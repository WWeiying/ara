// Synthetic Q4_K projection controls surround real captured quantized Attention.
// This is a lifetime/correctness fixture, not a performance benchmark. Acceptance
// also requires the parent to check the production traces between BEGIN/END:
// baseline: four native DIRECT Q4_K commands, no CROSS_OP or QUANT_KV execution;
// native: fill_keep + FILL, QUANT_KV success (16 commands/2 groups/256 decodes),
// then reuse_release + RELEASE, with the same AQ generation and activation_seq.
// A numerical PASS alone does not establish that either optimized path ran.
#include "ggml.h"
#include "ggml-alloc.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"
#include "repack.h"
#include "arch/riscv/qbs.h"

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

#if !defined(GGML_USE_RISCV_QUANT_KV) || !defined(__riscv)
#error "This fixture requires the RISC-V native quantized-KV integration"
#endif

static void require(bool ok, const char * reason) {
    if (!ok) {
        std::fprintf(stderr, "QUANT_INTERLEAVE_FAIL reason=%s\n", reason);
        std::exit(1);
    }
}

static void option(const char * name, const char * value) {
    require(setenv(name, value, 1) == 0, "setenv");
}

static std::vector<unsigned char> load(const std::string & path, size_t bytes) {
    std::ifstream file(path, std::ios::binary | std::ios::ate);
    if (!file || file.tellg() != static_cast<std::streamoff>(bytes)) {
        std::fprintf(stderr, "QUANT_INTERLEAVE_INPUT path=%s expected_bytes=%zu\n", path.c_str(), bytes);
        require(false, "capture_size_or_open");
    }
    file.seekg(0);
    std::vector<unsigned char> result(bytes);
    file.read(reinterpret_cast<char *>(result.data()), static_cast<std::streamsize>(bytes));
    require(file.good() && file.gcount() == static_cast<std::streamsize>(bytes), "capture_read");
    return result;
}

static uint64_t digest(const void * data, size_t bytes) {
    const auto * p = static_cast<const unsigned char *>(data);
    uint64_t hash = UINT64_C(14695981039346656037);
    for (size_t i = 0; i < bytes; ++i) hash = (hash ^ p[i]) * UINT64_C(1099511628211);
    return hash;
}

static float compare_attention(const std::vector<float> & actual, const std::vector<float> & expected) {
    require(actual.size() == 1536 && expected.size() == 1536, "attention_output_count");
    float maximum = 0;
    for (size_t i = 0; i < actual.size(); ++i) {
        const float error = std::fabs(actual[i] - expected[i]);
        if (!std::isfinite(actual[i]) || !std::isfinite(expected[i]) ||
            !std::isfinite(error) || error > 0.004f + 0.002f * std::fabs(expected[i])) {
            std::fprintf(stderr, "QUANT_INTERLEAVE_MISMATCH index=%zu actual=%.9g expected=%.9g\n",
                         i, static_cast<double>(actual[i]), static_cast<double>(expected[i]));
            require(false, "attention_tolerance");
        }
        if (error > maximum) maximum = error;
    }
    return maximum;
}

static std::vector<float> read_output(ggml_tensor * tensor, size_t elements) {
    require(ggml_nbytes(tensor) == elements * sizeof(float), "output_size");
    std::vector<float> result(elements);
    ggml_backend_tensor_get(tensor, result.data(), 0, elements * sizeof(float));
    for (float x : result) require(std::isfinite(x), "nonfinite_output");
    return result;
}

static void exact(const std::vector<float> & a, const std::vector<float> & b) {
    require(a.size() == b.size() && std::memcmp(a.data(), b.data(), a.size() * sizeof(float)) == 0,
            "projection_or_repeat_bits");
}

struct csr_snapshot {
    uintptr_t fcsr, vcsr;
};

static csr_snapshot compute(ggml_context * ctx, ggml_cgraph * graph) {
    __asm__ volatile("csrwi fcsr,0;csrwi vcsr,5" : : : "memory");
    const auto status = ggml_graph_compute_with_ctx(ctx, graph, 1);
    csr_snapshot csr{};
    __asm__ volatile("frcsr %0;csrr %1,vcsr" : "=r"(csr.fcsr), "=r"(csr.vcsr) : : "memory");
    require(status == GGML_STATUS_SUCCESS, "graph_compute");
    // Production Q8_K quantization selects VXRM=RNE; sticky VXSAT starts at1.
    if (csr.vcsr != 3) std::fprintf(stderr, "QUANT_INTERLEAVE_CSR expected_vcsr=3 actual=%lu\n", static_cast<unsigned long>(csr.vcsr));
    require(csr.vcsr == 3, "production_quantizer_vcsr_contract");
    return csr;
}

static void profile(bool q4) {
    const char * kind = q4 ? "q4_0" : "q8_0";
    const std::string directory = q4 ? "/q4" : "/q8";
    ggml_init_params init{};
    init.mem_size = 4 * 1024 * 1024;
    init.no_alloc = true;
    ggml_context * ctx = ggml_init(init);
    ggml_context * weight_ctx = ggml_init(init);
    require(ctx && weight_ctx, "context_allocation");

    // Two N tiles are required by the current activation-context planner.
    auto * weights = ggml_new_tensor_2d(weight_ctx, GGML_TYPE_Q4_K, 256, 64);
    ggml_set_name(weights, "interleave_synthetic_q4k_weights");
    auto weight_buffer = ggml_backend_alloc_ctx_tensors_from_buft(weight_ctx, ggml_backend_cpu_repack_buffer_type());
    require(weight_buffer && weights->extra, "repack_buffer_not_selected");
    const auto * traits = ggml_get_type_traits(GGML_TYPE_Q4_K);
    require(traits && traits->from_float_ref, "weight_quantizer_missing");
    const size_t row_bytes = ggml_row_size(GGML_TYPE_Q4_K, 256);
    require(row_bytes == 144 && ggml_nbytes(weights) == 64 * row_bytes, "weight_abi");
    std::vector<unsigned char> raw_weights(64 * row_bytes);
    std::vector<float> row(256);
    for (unsigned r = 0; r < 64; ++r) {
        for (unsigned i = 0; i < 256; ++i)
            row[i] = float(int((r * 29 + i * 17) % 127) - 63) / 512.0f;
        traits->from_float_ref(row.data(), raw_weights.data() + r * row_bytes, 256);
    }
    ggml_backend_tensor_set(weights, raw_weights.data(), 0, raw_weights.size());
    // With one K block, global R4 preserves these original row blocks.
    for (unsigned r = 0; r < 64; ++r) {
        const size_t index = (r / 4) * 4 + r % 4;
        require(std::memcmp(static_cast<const unsigned char *>(weights->data) + index * row_bytes,
                            raw_weights.data() + r * row_bytes, row_bytes) == 0, "r4_weight_mapping");
    }
    const std::vector<unsigned char> packed_weights(static_cast<const unsigned char *>(weights->data),
                                                   static_cast<const unsigned char *>(weights->data) + ggml_nbytes(weights));

    auto * activation = ggml_new_tensor_2d(ctx, GGML_TYPE_F32, 256, 1);
    auto * q = ggml_new_tensor_4d(ctx, GGML_TYPE_F32, 128, 1, 12, 1);
    auto * k = ggml_new_tensor_4d(ctx, q4 ? GGML_TYPE_Q4_0 : GGML_TYPE_Q8_0, 128, 256, 2, 1);
    auto * v = ggml_new_tensor_4d(ctx, GGML_TYPE_Q8_0, 128, 256, 2, 1);
    auto * mask = ggml_new_tensor_4d(ctx, GGML_TYPE_F16, 256, 1, 1, 1);
    ggml_set_name(activation, "interleave_synthetic_A");
    ggml_set_name(q, "interleave_real_B");
    auto * proj1 = ggml_mul_mat(ctx, weights, activation);
    const uint32_t scale_bits = UINT32_C(0x3db504f3);
    float scale;
    std::memcpy(&scale, &scale_bits, sizeof(scale));
    auto * attention = ggml_flash_attn_ext(ctx, q, k, v, mask, scale, 0, 0);
    auto * proj2 = ggml_mul_mat(ctx, weights, activation);
    ggml_set_name(proj1, "interleave_projection_before");
    ggml_set_name(attention, "interleave_real_attention");
    ggml_set_name(proj2, "interleave_projection_after");
    auto * graph = ggml_new_graph(ctx);
    ggml_build_forward_expand(graph, proj1);
    ggml_build_forward_expand(graph, attention);
    ggml_build_forward_expand(graph, proj2);
    require(proj1 != proj2 && proj1->src[1] == activation && proj2->src[1] == activation,
            "shared_activation_consumers");
    require(ggml_graph_n_nodes(graph) == 3 && ggml_graph_node(graph, 0) == proj1 &&
            ggml_graph_node(graph, 1) == attention && ggml_graph_node(graph, 2) == proj2,
            "interleave_node_order");
    auto buffer = ggml_backend_alloc_ctx_tensors_from_buft(ctx, ggml_backend_cpu_buffer_type());
    require(buffer && activation->data != q->data, "tensor_allocation");

    std::vector<float> a(256);
    for (unsigned i = 0; i < 256; ++i)
        a[i] = float(i == 0 ? 127 : int((i * 23) % 193) - 96) / 256.0f;
    ggml_backend_tensor_set(activation, a.data(), 0, a.size() * sizeof(float));
    ggml_tensor * inputs[] = {q, k, v, mask};
    const char * files[] = {"attn_q_input-0.bin", "attn_k_input-0.bin", "attn_v_input-0.bin", "attn_mask_input-0.bin"};
    std::vector<unsigned char> captures[4];
    for (unsigned i = 0; i < 4; ++i) {
        captures[i] = load(directory + "/" + files[i], ggml_nbytes(inputs[i]));
        ggml_backend_tensor_set(inputs[i], captures[i].data(), 0, captures[i].size());
        std::printf("QUANT_INTERLEAVE_INPUT kind=%s file=%s bytes=%zu digest=%016llx\n", kind, files[i],
                    captures[i].size(), static_cast<unsigned long long>(digest(captures[i].data(), captures[i].size())));
    }
    require(std::memcmp(a.data(), captures[0].data(), a.size() * sizeof(float)) != 0, "A_equals_B_prefix");
    for (unsigned i = 0; i < 256; ++i) {
        uint16_t bits;
        std::memcpy(&bits, captures[3].data() + i * sizeof(bits), sizeof(bits));
        require(i < 128 ? (bits & UINT16_C(0x7fff)) == 0 : bits == UINT16_C(0xfc00), "visible_prefix_not_128");
    }
    const auto gold_bytes = load(directory + "/kqv_out-0.bin", 6144);
    std::vector<float> gold(1536);
    std::memcpy(gold.data(), gold_bytes.data(), gold_bytes.size());
    std::printf("QUANT_INTERLEAVE_GRAPH kind=%s nodes=3 order=projection,attention,projection "
                "projection=synthetic_q4k_m1_n64_k256 attention=real_d128_h12_kvh2_visible128_capacity256 "
                "gold_digest=%016llx A=%p B=%p\n", kind,
                static_cast<unsigned long long>(digest(gold_bytes.data(), gold_bytes.size())), activation->data, q->data);

    std::vector<float> baseline_projection, baseline_attention, previous_attention;
    csr_snapshot baseline_csr{};
    for (unsigned run = 0; run < 3; ++run) {
        const bool native = run != 0;
        option("GGML_RISCV_QBS_ACTIVATION_CONTEXT", native ? "1" : "0");
        option("GGML_RISCV_QBS_CROSS_OP_CONTEXT", native ? "1" : "0");
        option("GGML_RISCV_AKV_QUANT_KV", native ? "1" : "0");
        for (auto * output : {proj1, attention, proj2}) {
            const std::vector<uint32_t> poison(ggml_nbytes(output) / 4, UINT32_C(0x7fc00001));
            ggml_backend_tensor_set(output, poison.data(), 0, ggml_nbytes(output));
        }
        std::printf("QUANT_INTERLEAVE_BEGIN kind=%s run=%u mode=%s context=%u cross_op=%u quant_kv=%u threads=1\n",
                    kind, run, native ? "native" : "baseline", unsigned(native), unsigned(native), unsigned(native));
        const csr_snapshot csr = compute(ctx, graph);
        const auto before = read_output(proj1, 64);
        const auto after = read_output(proj2, 64);
        const auto actual = read_output(attention, 1536);
        exact(before, after);
        const float gold_error = compare_attention(actual, gold);
        float ordinary_error = 0;
        if (!native) {
            baseline_projection = before;
            baseline_attention = actual;
            baseline_csr = csr;
        } else {
            exact(before, baseline_projection);
            ordinary_error = compare_attention(actual, baseline_attention);
            require(csr.fcsr == baseline_csr.fcsr && csr.vcsr == baseline_csr.vcsr, "baseline_csr_mismatch");
            if (run == 2) exact(actual, previous_attention);
            previous_attention = actual;
        }
        require(std::memcmp(activation->data, a.data(), a.size() * sizeof(float)) == 0, "A_modified");
        require(std::memcmp(weights->data, packed_weights.data(), packed_weights.size()) == 0, "weights_modified");
        for (unsigned i = 0; i < 4; ++i)
            require(std::memcmp(inputs[i]->data, captures[i].data(), captures[i].size()) == 0, "capture_input_modified");
        std::printf("QUANT_INTERLEAVE_END kind=%s run=%u mode=%s projection_outputs=128 attention_outputs=1536 "
                    "projection_digest=%016llx attention_digest=%016llx fcsr=%lu vcsr=%lu "
                    "gold_max_abs=%.9g ordinary_max_abs=%.9g inputs_unchanged=1\n", kind, run,
                    native ? "native" : "baseline",
                    static_cast<unsigned long long>(digest(before.data(), before.size() * sizeof(float))),
                    static_cast<unsigned long long>(digest(actual.data(), actual.size() * sizeof(float))),
                    static_cast<unsigned long>(csr.fcsr), static_cast<unsigned long>(csr.vcsr),
                    static_cast<double>(gold_error), static_cast<double>(ordinary_error));
    }
    std::printf("QUANT_INTERLEAVE_PROFILE_NUMERICAL_PASS kind=%s runs=3 native_runs=2 trace_validation_required=1\n", kind);
    ggml_backend_buffer_free(buffer);
    ggml_free(ctx);
    ggml_backend_buffer_free(weight_buffer);
    ggml_free(weight_ctx);
}

int main() {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    std::setvbuf(stderr, nullptr, _IONBF, 0);
    option("GGML_RISCV_QBS", "1");
    option("GGML_RISCV_QBS_EMULATE", "0");
    option("GGML_RISCV_QBS_SEGMENT_K_BLOCKS", "0");
    option("GGML_RISCV_QBS_WIDE_M", "0");
    option("GGML_RISCV_QBS_TRACE", "1");
    option("GGML_RISCV_QBS_TRACE_CALLS", "1");
    option("GGML_RISCV_QBS_TRACE_LIFETIME", "1");
    option("GGML_RISCV_AKV", "0");
    option("GGML_RISCV_AKV_EMULATE", "0");
    option("GGML_RISCV_AKV_TRACE", "1");
    option("GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY", "1");
    ggml_cpu_init();
    const qbs_device_t * device = ggml_riscv_qbs_direct_device();
    require(device != nullptr, "native_device_missing");
    const qbs_problem_t problem = {QBS_WEIGHT_PROFILE_Q4_K, QBS_ACTIVATION_PROFILE_Q8_K,
                                  QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR, QBS_ACTIVATION_STORAGE_ROW_MAJOR,
                                  1, 64, 256};
    qbs_plan_t plan{};
    require(qbs_plan_create(device, &problem, &plan) == QBS_STATUS_OK &&
            qbs_plan_supports_activation_context(&plan), "projection_context_unsupported");
    require(ggml_riscv_qbs_supports_tensor(GGML_TYPE_Q4_K, 256, 64), "projection_native_not_selected");
    profile(false);
    profile(true);
    std::puts("QUANT_INTERLEAVE_SUITE_NUMERICAL_PASS profiles=2 runs=6 native_runs=4 "
              "trace_validation_required=1 performance=not_measured");
    return 0;
}
