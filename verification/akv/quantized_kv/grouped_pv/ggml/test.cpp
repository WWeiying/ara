// Actual GGML graphs on captured operands. Physical token-major K/V remain
// strided views at dispatch; only the production runtime may gather K panels.
#include "ggml.h"
#include "ggml-alloc.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

#if !defined(__riscv) || __riscv_xlen != 64
#error "Native RISC-V graph fixture required"
#endif

static constexpr unsigned DIM = 128, CAPACITY = 256, KV_HEADS = 2, Q_HEADS = 12;
static constexpr size_t OUTPUTS = DIM * Q_HEADS, OUTPUT_BYTES = OUTPUTS * sizeof(float);

static void require(bool ok, const char * reason) {
    if (!ok) {
        std::fprintf(stderr, "GROUPED_GGML_FAIL reason=%s\n", reason);
        std::exit(1);
    }
}

static void option(const char * name, const char * value) {
    require(setenv(name, value, 1) == 0, "setenv");
}

static std::vector<unsigned char> load(const std::string & path, size_t bytes) {
    std::ifstream file(path, std::ios::binary | std::ios::ate);
    if (!file || file.tellg() != static_cast<std::streamoff>(bytes)) {
        std::fprintf(stderr, "GROUPED_GGML_FAIL reason=capture_size path=%s bytes=%zu\n", path.c_str(), bytes);
        std::exit(1);
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

static float compare(const std::vector<float> & actual, const std::vector<float> & expected) {
    require(actual.size() == OUTPUTS && expected.size() == OUTPUTS, "output_count");
    float maximum = 0;
    for (size_t i = 0; i < OUTPUTS; ++i) {
        const float error = std::fabs(actual[i] - expected[i]);
        if (!std::isfinite(actual[i]) || !std::isfinite(expected[i]) ||
            !std::isfinite(error) || error > 0.004f + 0.002f * std::fabs(expected[i])) {
            std::fprintf(stderr, "GROUPED_GGML_FAIL reason=numerical index=%zu actual=%.9g expected=%.9g\n",
                         i, static_cast<double>(actual[i]), static_cast<double>(expected[i]));
            std::exit(1);
        }
        if (error > maximum) maximum = error;
    }
    return maximum;
}

struct result {
    std::vector<float> output;
    uintptr_t fcsr, vcsr;
};

static void same_csr(const result & a, const result & b) {
    if (a.fcsr != b.fcsr || a.vcsr != b.vcsr)
        std::fprintf(stderr, "GROUPED_GGML_CSR_DIAG contract=exact actual_fcsr=%lu ref_fcsr=%lu fcsr_xor=%lu actual_vcsr=%lu ref_vcsr=%lu\n",
                     static_cast<unsigned long>(a.fcsr), static_cast<unsigned long>(b.fcsr),
                     static_cast<unsigned long>(a.fcsr ^ b.fcsr),
                     static_cast<unsigned long>(a.vcsr), static_cast<unsigned long>(b.vcsr));
    require(a.fcsr == b.fcsr && a.vcsr == b.vcsr, "baseline_csr_mismatch");
}

static void same_bits(const result & a, const result & b) {
    require(a.output.size() == OUTPUTS && b.output.size() == OUTPUTS &&
            !std::memcmp(a.output.data(), b.output.data(), OUTPUT_BYTES), "repeat_or_fallback_bits");
}

struct capture {
    std::vector<unsigned char> query, key, value, mask;
    std::vector<float> golden;
    size_t key_row;

    explicit capture(bool q4) : key_row(q4 ? 72 : 136) {
        const std::string directory = q4 ? "/q4/" : "/q8/";
        query = load(directory + "attn_q_input-0.bin", OUTPUT_BYTES);
        key = load(directory + "attn_k_input-0.bin", CAPACITY * KV_HEADS * key_row);
        value = load(directory + "attn_v_input-0.bin", CAPACITY * KV_HEADS * 136);
        mask = load(directory + "attn_mask_input-0.bin", CAPACITY * 2);
        const auto raw = load(directory + "kqv_out-0.bin", OUTPUT_BYTES);
        golden.resize(OUTPUTS);
        std::memcpy(golden.data(), raw.data(), raw.size());
        for (unsigned t = 0; t < CAPACITY; ++t) {
            uint16_t bits;
            std::memcpy(&bits, mask.data() + t * 2, 2);
            require(bits == (t < 128 ? 0 : UINT16_C(0xfc00)), "capture_mask_not_prefix128");
        }
    }
};

// This is a byte-coordinate permutation, not dequantization or normalization.
static std::vector<unsigned char> physical_bytes(const std::vector<unsigned char> & source,
                                                size_t row, bool token_major) {
    require(source.size() == CAPACITY * KV_HEADS * row, "capture_row_size");
    if (!token_major) return source;
    std::vector<unsigned char> result(source.size());
    for (unsigned t = 0; t < CAPACITY; ++t)
        for (unsigned h = 0; h < KV_HEADS; ++h)
            std::memcpy(result.data() + (t * KV_HEADS + h) * row,
                        source.data() + (h * CAPACITY + t) * row, row);
    return result;
}

struct graph_fixture {
    const capture & data;
    const bool token_major;
    ggml_context * ctx;
    ggml_backend_buffer_t buffer;
    ggml_tensor * q, * key_backing, * value_backing, * k, * v, * mask, * dst;
    ggml_cgraph * graph;
    std::vector<unsigned char> key_bytes, value_bytes;
    std::vector<uint16_t> active_mask;
    uint64_t query_digest, key_digest, value_digest;

    graph_fixture(const capture & source, bool q4, bool strided) : data(source), token_major(strided) {
        ggml_init_params init{};
        init.mem_size = 4 * 1024 * 1024;
        init.no_alloc = true;
        ctx = ggml_init(init);
        require(ctx != nullptr, "context_allocation");
        q = ggml_new_tensor_4d(ctx, GGML_TYPE_F32, DIM, 1, Q_HEADS, 1);
        key_backing = ggml_new_tensor_4d(ctx, q4 ? GGML_TYPE_Q4_0 : GGML_TYPE_Q8_0,
                                       DIM, strided ? KV_HEADS : CAPACITY, strided ? CAPACITY : KV_HEADS, 1);
        value_backing = ggml_new_tensor_4d(ctx, GGML_TYPE_Q8_0,
                                         DIM, strided ? KV_HEADS : CAPACITY, strided ? CAPACITY : KV_HEADS, 1);
        k = strided ? ggml_permute(ctx, key_backing, 0, 2, 1, 3) : key_backing;
        v = strided ? ggml_permute(ctx, value_backing, 0, 2, 1, 3) : value_backing;
        mask = ggml_new_tensor_4d(ctx, GGML_TYPE_F16, CAPACITY, 1, 1, 1);
        const uint32_t scale_bits = UINT32_C(0x3db504f3);
        float scale;
        std::memcpy(&scale, &scale_bits, sizeof(scale));
        dst = ggml_flash_attn_ext(ctx, q, k, v, mask, scale, 0, 0);
        graph = ggml_new_graph(ctx);
        ggml_build_forward_expand(graph, dst);
        require(ggml_graph_n_nodes(graph) == (strided ? 3 : 1), "unexpected_graph_nodes");
        if (strided)
            require(ggml_graph_node(graph, 0) == k && ggml_graph_node(graph, 1) == v &&
                    k->op == GGML_OP_PERMUTE && v->op == GGML_OP_PERMUTE, "view_graph_order");
        require(ggml_graph_node(graph, ggml_graph_n_nodes(graph) - 1) == dst &&
                dst->src[1] == k && dst->src[2] == v, "attention_not_using_original_views");
        buffer = ggml_backend_alloc_ctx_tensors_from_buft(ctx, ggml_backend_cpu_buffer_type());
        require(buffer != nullptr, "tensor_allocation");
        require(ggml_nbytes(dst) == OUTPUT_BYTES, "output_capacity");
        key_bytes = physical_bytes(data.key, data.key_row, strided);
        value_bytes = physical_bytes(data.value, 136, strided);
        ggml_backend_tensor_set(q, data.query.data(), 0, data.query.size());
        ggml_backend_tensor_set(key_backing, key_bytes.data(), 0, key_bytes.size());
        ggml_backend_tensor_set(value_backing, value_bytes.data(), 0, value_bytes.size());
        active_mask.resize(CAPACITY);
        std::memcpy(active_mask.data(), data.mask.data(), data.mask.size());
        upload_mask();
        query_digest = digest(data.query.data(), data.query.size());
        key_digest = digest(key_bytes.data(), key_bytes.size());
        value_digest = digest(value_bytes.data(), value_bytes.size());
        unchanged();
    }

    ~graph_fixture() { ggml_backend_buffer_free(buffer); ggml_free(ctx); }
    graph_fixture(const graph_fixture &) = delete;
    graph_fixture & operator=(const graph_fixture &) = delete;

    void upload_mask() {
        ggml_backend_tensor_set(mask, active_mask.data(), 0, active_mask.size() * sizeof(uint16_t));
    }

    void prefix(unsigned visible, bool hole = false) {
        require(visible == 128 || visible == 5, "unexpected_prefix");
        std::memcpy(active_mask.data(), data.mask.data(), data.mask.size());
        for (unsigned t = visible; t < CAPACITY; ++t) active_mask[t] = UINT16_C(0xfc00);
        if (hole) { require(visible == 128, "hole_prefix"); active_mask[63] = UINT16_C(0xfc00); }
        upload_mask();
    }

    void unchanged() const {
        require(q->ne[0] == DIM && q->ne[1] == 1 && q->ne[2] == Q_HEADS && q->ne[3] == 1 &&
                q->nb[0] == 4 && q->nb[2] == DIM * 4 && ggml_nbytes(q) == data.query.size(), "query_metadata");
        require(!std::memcmp(q->data, data.query.data(), data.query.size()) &&
                digest(q->data, data.query.size()) == query_digest, "query_changed");
        require(ggml_nbytes(key_backing) == key_bytes.size() && ggml_nbytes(value_backing) == value_bytes.size(),
                "backing_capacity_changed");
        require(!std::memcmp(key_backing->data, key_bytes.data(), key_bytes.size()) &&
                digest(key_backing->data, key_bytes.size()) == key_digest, "key_backing_changed");
        require(!std::memcmp(value_backing->data, value_bytes.data(), value_bytes.size()) &&
                digest(value_backing->data, value_bytes.size()) == value_digest, "value_backing_changed");
        require(!std::memcmp(mask->data, active_mask.data(), CAPACITY * 2), "mask_changed");
        for (unsigned which = 0; which < 2; ++which) {
            const auto * view = which ? v : k;
            const auto * backing = which ? value_backing : key_backing;
            const auto & raw = which ? data.value : data.key;
            const size_t row = which ? 136 : data.key_row;
            require(view->data == backing->data && view->ne[0] == DIM && view->ne[1] == CAPACITY &&
                    view->ne[2] == KV_HEADS && view->ne[3] == 1 && view->nb[0] == row / 4 &&
                    view->nb[1] == (token_major ? KV_HEADS * row : row) &&
                    view->nb[2] == (token_major ? row : CAPACITY * row) &&
                    view->nb[3] == raw.size() && ggml_nbytes(view) == raw.size(), "physical_view_metadata");
            if (token_major) require(view->view_src == backing && view->view_offs == 0, "view_backing_changed");
            for (unsigned h = 0; h < KV_HEADS; ++h)
                for (unsigned t = 0; t < CAPACITY; ++t)
                    require(!std::memcmp(static_cast<const unsigned char *>(view->data) + h * view->nb[2] + t * view->nb[1],
                                         raw.data() + (h * CAPACITY + t) * row, row), "logical_row_changed");
        }
    }

    result compute(int threads, bool reference = false, unsigned frm = 0) {
        const std::vector<uint32_t> poison(OUTPUTS, UINT32_C(0x7fc00001));
        ggml_backend_tensor_set(dst, poison.data(), 0, OUTPUT_BYTES);
        result answer{std::vector<float>(OUTPUTS), 0, 0};
        auto plan = ggml_graph_plan(graph, threads, nullptr);
        plan.use_ref = reference;
        std::vector<uint8_t> work(plan.work_size);
        plan.work_data = work.empty() ? nullptr : work.data();
        const uintptr_t initial = (frm << 5) | 8u; // Keep a preexisting DZ flag.
        __asm__ volatile("csrw fcsr,%0;csrwi vcsr,5;csrwi vstart,0" : : "r"(initial) : "memory");
        const auto status = ggml_graph_compute(graph, &plan);
        __asm__ volatile("frcsr %0;csrr %1,vcsr" : "=r"(answer.fcsr), "=r"(answer.vcsr) : : "memory");
        require(status == GGML_STATUS_SUCCESS, "graph_compute");
        if ((answer.fcsr & ~uintptr_t(31)) != (frm << 5) || !(answer.fcsr & 8u) || answer.vcsr != 5)
            std::fprintf(stderr, "GROUPED_GGML_CSR_DIAG contract=preservation actual_fcsr=%lu expected_frm=%u actual_vcsr=%lu preset_dz=8\n",
                         static_cast<unsigned long>(answer.fcsr), frm, static_cast<unsigned long>(answer.vcsr));
        require((answer.fcsr & ~uintptr_t(31)) == (frm << 5) &&
                (answer.fcsr & 8u) && answer.vcsr == 5, "csr_preservation");
        ggml_backend_tensor_get(dst, answer.output.data(), 0, OUTPUT_BYTES);
        for (float value : answer.output) require(std::isfinite(value), "nonfinite_output");
        unchanged();
        return answer;
    }
};


static void grouped_option(unsigned grouped) {
    if (!grouped) require(unsetenv("GGML_RISCV_AKV_GROUPED_PV") == 0, "unsetenv");
    else option("GGML_RISCV_AKV_GROUPED_PV", "1");
}

static void native_cases(graph_fixture & fixture, const char * kind, const char * layout) {
    for (unsigned visible : {128u, 5u}) {
        fixture.prefix(visible);
        option("GGML_RISCV_AKV_QUANT_KV", "0");
        const result reference = fixture.compute(1, true);
        const result ordinary = fixture.compute(1);
        compare(ordinary.output, reference.output);
        same_csr(ordinary, reference);
        if (visible == 128) compare(reference.output, fixture.data.golden);
        option("GGML_RISCV_AKV_QUANT_KV", "1");
        result previous[2]{};
        for (unsigned repeat = 0; repeat < 2; ++repeat) {
            result pair[2]{};
            for (unsigned grouped = 0; grouped < 2; ++grouped) {
                grouped_option(grouped);
                std::printf("GROUPED_GGML_BEGIN kind=%s layout=%s mode=native visible=%u repeat=%u grouped=%u\n",
                            kind, layout, visible, repeat, grouped);
                pair[grouped] = fixture.compute(1);
                const float error = compare(pair[grouped].output, reference.output);
                if (visible == 128) compare(pair[grouped].output, fixture.data.golden);
                same_csr(pair[grouped], reference);
                if (repeat) {
                    same_bits(pair[grouped], previous[grouped]);
                    same_csr(pair[grouped], previous[grouped]);
                }
                if (grouped) {
                    same_bits(pair[0], pair[1]);
                    same_csr(pair[0], pair[1]);
                }
                previous[grouped] = pair[grouped];
                std::printf("GROUPED_GGML_END kind=%s layout=%s mode=native visible=%u repeat=%u grouped=%u outputs=1536 flags=%lu ref_flags=%lu vcsr=%lu max_abs=%.9g exact_pair=%u\n",
                            kind, layout, visible, repeat, grouped,
                            static_cast<unsigned long>(pair[grouped].fcsr),
                            static_cast<unsigned long>(reference.fcsr),
                            static_cast<unsigned long>(pair[grouped].vcsr),
                            static_cast<double>(error), grouped);
            }
        }
    }
}

static void fallback_cases(graph_fixture & fixture, const char * kind) {
    const char * modes[] = {"mask", "thread", "memory", "rounding", "reference"};
    for (unsigned mode = 0; mode < 5; ++mode) {
        fixture.prefix(128, mode == 0);
        const int threads = mode == 1 ? 2 : 1;
        const unsigned frm = mode == 3 ? 1 : 0; // RTZ must not enter QBS.
        const bool reference = mode == 4;
        option("GGML_RISCV_AKV_QUANT_KV", "0");
        option("GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY", mode == 2 ? "0" : "1");
        const result ordinary = fixture.compute(threads, reference, frm);
        option("GGML_RISCV_AKV_QUANT_KV", "1");
        for (unsigned grouped = 0; grouped < 2; ++grouped) {
            grouped_option(grouped);
            std::printf("GROUPED_GGML_BEGIN kind=%s layout=token_major mode=%s grouped=%u\n",
                        kind, modes[mode], grouped);
            const result actual = fixture.compute(threads, reference, frm);
            if (threads == 2)
                std::printf("GROUPED_GGML_THREAD_CSR kind=%s mode=thread grouped=%u actual_fcsr=%lu ref_fcsr=%lu actual_vcsr=%lu ref_vcsr=%lu actual_new_flags=%lu ref_new_flags=%lu aggregate=0\n",
                            kind, grouped, static_cast<unsigned long>(actual.fcsr),
                            static_cast<unsigned long>(ordinary.fcsr), static_cast<unsigned long>(actual.vcsr),
                            static_cast<unsigned long>(ordinary.vcsr),
                            static_cast<unsigned long>(actual.fcsr & 23u),
                            static_cast<unsigned long>(ordinary.fcsr & 23u));
            same_bits(actual, ordinary);
            if (threads == 2) {
                // Dynamic head scheduling does not aggregate worker fflags.
                require((actual.fcsr & ~uintptr_t(31)) == (ordinary.fcsr & ~uintptr_t(31)) &&
                        (actual.fcsr & 8u) && (ordinary.fcsr & 8u) &&
                        actual.vcsr == 5 && ordinary.vcsr == 5, "thread_csr_preservation");
            } else {
                same_csr(actual, ordinary);
            }
            std::printf("GROUPED_GGML_END kind=%s layout=token_major mode=%s grouped=%u outputs=1536 flags=%lu ref_flags=%lu vcsr=%lu exact=1\n",
                        kind, modes[mode], grouped, static_cast<unsigned long>(actual.fcsr),
                        static_cast<unsigned long>(ordinary.fcsr), static_cast<unsigned long>(actual.vcsr));
        }
    }
    option("GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY", "1");
    fixture.prefix(128);
}

static void profile(bool q4) {
    const char * kind = q4 ? "q4_0" : "q8_0";
    const capture data(q4);
    {
        graph_fixture contiguous(data, q4, false);
        native_cases(contiguous, kind, "contiguous");
    }
    {
        graph_fixture token_major(data, q4, true);
        native_cases(token_major, kind, "token_major");
        fallback_cases(token_major, kind);
    }
    std::printf("GROUPED_GGML_PROFILE_PASS kind=%s outputs=1536 native_calls=16 fallback_calls=10 inputs_unchanged=1\n", kind);
}

int main() {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    std::setvbuf(stderr, nullptr, _IONBF, 0);
    option("GGML_RISCV_QBS", "1");
    option("GGML_RISCV_QBS_EMULATE", "0");
    option("GGML_RISCV_AKV", "0");
    option("GGML_RISCV_AKV_EMULATE", "0");
    option("GGML_RISCV_AKV_TRACE", "1");
    option("GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY", "1");
    grouped_option(0);
    ggml_cpu_init();
    profile(false);
    profile(true);
    std::puts("GROUPED_GGML_SUITE_PASS profiles=2 layouts=2 native_calls=32 fallback_calls=20 executor=native_qbs performance=not_measured");
    return 0;
}
