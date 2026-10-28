#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"
#include "ggml-quants.h"
#include "repack.h"
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static constexpr int K = 256, N = 8, GUARD = 16;

static void need(bool ok, const char * reason) {
    if (!ok) {
        std::printf("M4_STRIDE_ERROR reason=%s\n", reason);
        std::exit(2);
    }
}

static uint32_t bits(float value) {
    uint32_t result;
    std::memcpy(&result, &value, sizeof(result));
    return result;
}

struct Observation {
    const char * type;
    int m, pad;
    ggml_tensor * weights;
    ggml_tensor * inputs[2];
    ggml_tensor * outputs[2];
    void * addresses[2];
    unsigned before[2] = {}, after[2] = {};
};

static bool observe(ggml_tensor * node, bool ask, void * opaque) {
    auto & o = *static_cast<Observation *>(opaque);
    need(node->op == GGML_OP_VIEW || node->op == GGML_OP_MUL_MAT, "scheduler_added_operation");
    if (node->op != GGML_OP_MUL_MAT) return false;
    const int side = node == o.outputs[0] ? 0 : 1;
    need(node == o.outputs[side] && node->src[0] == o.weights, "scheduled_weights_or_output");
    auto * x = node->src[1];
    const size_t stride = size_t(K + (side ? o.pad : 0)) * sizeof(float);
    need(x == o.inputs[side] && x->data == o.addresses[side], "scheduler_replaced_input");
    need(x->op == GGML_OP_VIEW && x->view_src &&
         x->data == static_cast<char *>(x->view_src->data) + GUARD * sizeof(float), "view_identity");
    need(x->nb[0] == sizeof(float) && x->nb[1] == stride &&
         x->ne[0] == K && x->ne[1] == o.m, "scheduled_stride_or_shape");
    need(ggml_is_contiguous(x) == (side == 0 || o.pad == 0), "scheduled_contiguity");
    (ask ? o.before[side] : o.after[side])++;
    std::printf("M4_STRIDE_OBSERVE type=%s k=%d n=%d m=%d pad=%d side=%d phase=%s "
                "nb0=%zu nb1=%zu contiguous=%d same_tensor=1 same_data=1\n",
                o.type, K, N, o.m, o.pad, side, ask ? "before" : "after",
                x->nb[0], x->nb[1], int(ggml_is_contiguous(x)));
    return true;
}

static unsigned run_case(ggml_type type, int m, int pad, const std::vector<float> & activation) {
    const char * name = type == GGML_TYPE_Q4_K ? "Q4_K" : "Q6_K";
    std::printf("M4_STRIDE_BEGIN type=%s k=%d n=%d m=%d pad=%d\n", name, K, N, m, pad);
    ggml_init_params params{2 * 1024 * 1024, nullptr, true};
    auto * wc = ggml_init(params);
    auto * ctx = ggml_init(params);
    need(wc && ctx, "contexts");
    auto * w = ggml_new_tensor_2d(wc, type, K, N);
    auto * wb = ggml_backend_alloc_ctx_tensors_from_buft(wc, ggml_backend_cpu_repack_buffer_type());
    need(wb && w->extra, "repacked_weights");
    ggml_backend_buffer_clear(wb, 0xa5);
    std::vector<float> weights(K * N);
    for (int i = 0; i < K * N; ++i) weights[i] = float((i * 17 + (i / K) * 3) % 127 - 63) / 512;
    const auto weights_before = weights;
    std::vector<unsigned char> raw(ggml_row_size(type, K) * N);
    if (type == GGML_TYPE_Q4_K) {
        quantize_row_q4_K_ref(weights.data(), reinterpret_cast<block_q4_K *>(raw.data()), K * N);
    } else {
        quantize_row_q6_K_ref(weights.data(), reinterpret_cast<block_q6_K *>(raw.data()), K * N);
    }
    const auto raw_before = raw;
    ggml_backend_tensor_set(w, raw.data(), 0, raw.size());
    // CPU_REPACK has no get_tensor API. Snapshot its entire host allocation,
    // including alignment bytes, after the legitimate repacking write.
    const auto * packed = static_cast<const unsigned char *>(ggml_backend_buffer_get_base(wb));
    const size_t packed_size = ggml_backend_buffer_get_size(wb);
    const std::vector<unsigned char> packed_before(packed, packed + packed_size);
    void * const weight_extra = w->extra;
    void * const weight_data = w->data;

    auto * backend = ggml_backend_cpu_init();
    need(backend, "backend");
    ggml_backend_cpu_set_n_threads(backend, 1);
    ggml_tensor * backing[2], * x[2], * y[2];
    std::vector<float> storage[2];
    auto * graph = ggml_new_graph(ctx);
    for (int side = 0; side < 2; ++side) {
        const int stride = K + (side ? pad : 0);
        storage[side].resize(GUARD + m * stride + GUARD);
        for (size_t i = 0; i < storage[side].size(); ++i) {
            storage[side][i] = 19.0f + float(i % 31) / 8;
        }
        for (int row = 0; row < m; ++row) {
            std::memcpy(storage[side].data() + GUARD + row * stride,
                        activation.data() + row * K, K * sizeof(float));
        }
        backing[side] = ggml_new_tensor_1d(ctx, GGML_TYPE_F32, storage[side].size());
        ggml_set_input(backing[side]);
        x[side] = ggml_view_2d(ctx, backing[side], K, m, stride * sizeof(float), GUARD * sizeof(float));
        y[side] = ggml_mul_mat(ctx, w, x[side]);
        ggml_set_output(y[side]);
        ggml_build_forward_expand(graph, y[side]);
    }
    auto * buffer = ggml_backend_alloc_ctx_tensors(ctx, backend);
    need(buffer, "activation_buffer");
    std::vector<uint32_t> unwritten(N * m, UINT32_C(0x7fc00001));
    for (int side = 0; side < 2; ++side) {
        ggml_backend_tensor_set(backing[side], storage[side].data(), 0, storage[side].size() * sizeof(float));
        ggml_backend_tensor_set(y[side], unwritten.data(), 0, unwritten.size() * sizeof(uint32_t));
        need(ggml_backend_supports_op(backend, y[side]), "backend_rejects_view");
    }
    need(std::strcmp(ggml_backend_buffer_name(wb), "CPU_REPACK") == 0, "weight_buffer_type");
    for (int row = 0; row < m; ++row) {
        need(std::memcmp(static_cast<char *>(x[0]->data) + row * x[0]->nb[1],
                         static_cast<char *>(x[1]->data) + row * x[1]->nb[1], K * sizeof(float)) == 0,
             "paired_input_values");
    }
    Observation observation{name, m, pad, w, {x[0], x[1]}, {y[0], y[1]}, {x[0]->data, x[1]->data}};
    auto * sched = ggml_backend_sched_new(&backend, nullptr, 1, GGML_DEFAULT_GRAPH_SIZE, false, false);
    need(sched, "scheduler");
    ggml_backend_sched_set_eval_callback(sched, observe, &observation);
    need(ggml_backend_sched_alloc_graph(sched, graph), "scheduler_allocation");
    const auto status = ggml_backend_sched_graph_compute(sched, graph);
    need(status == GGML_STATUS_SUCCESS, "complete_graph_status");
    for (int side = 0; side < 2; ++side) {
        need(observation.before[side] == 1 && observation.after[side] == 1, "complete_graph_callbacks");
        std::vector<float> after(storage[side].size());
        ggml_backend_tensor_get(backing[side], after.data(), 0, after.size() * sizeof(float));
        need(std::memcmp(after.data(), storage[side].data(), after.size() * sizeof(float)) == 0,
             "full_activation_backing_integrity");
    }
    need(w->extra == weight_extra && w->data == weight_data &&
         std::memcmp(packed, packed_before.data(), packed_size) == 0, "full_repacked_weight_integrity");
    need(raw == raw_before && std::memcmp(weights.data(), weights_before.data(), weights.size() * sizeof(float)) == 0,
         "weight_source_integrity");
    std::vector<float> result[2] = {std::vector<float>(N * m), std::vector<float>(N * m)};
    for (int side = 0; side < 2; ++side) {
        ggml_backend_tensor_get(y[side], result[side].data(), 0, result[side].size() * sizeof(float));
    }
    unsigned mismatches = 0, equal_rows = (1u << m) - 1;
    for (int i = 0; i < N * m; ++i) {
        const float ref = result[0][i], got = result[1][i];
        need(std::isfinite(ref) && std::isfinite(got), "finite_complete_outputs");
        const bool equal = bits(ref) == bits(got);
        std::printf("M4_STRIDE_VALUE type=%s k=%d n=%d m=%d pad=%d index=%d row=%d col=%d "
                    "ref=%.9g got=%.9g ref_bits=%08x got_bits=%08x\n",
                    name, K, N, m, pad, i, i / N, i % N, double(ref), double(got), bits(ref), bits(got));
        if (!equal) {
            if (mismatches == 0) {
                std::printf("M4_STRIDE_FIRST_MISMATCH type=%s k=%d n=%d m=%d pad=%d index=%d row=%d col=%d "
                            "ref=%.9g got=%.9g ref_bits=%08x got_bits=%08x\n",
                            name, K, N, m, pad, i, i / N, i % N, double(ref), double(got), bits(ref), bits(got));
            }
            ++mismatches;
            equal_rows &= ~(1u << (i / N));
        }
    }
    std::printf("M4_STRIDE_CASE type=%s k=%d n=%d m=%d pad=%d graph_status=%d "
                "complete=1 finite=1 input_integrity=1 mismatches=%u equal_rows=%u result=%s\n",
                name, K, N, m, pad, int(status), mismatches, equal_rows, mismatches ? "FAIL" : "PASS");
    ggml_backend_sched_free(sched);
    ggml_backend_buffer_free(buffer);
    ggml_backend_free(backend);
    ggml_backend_buffer_free(wb);
    ggml_free(ctx);
    ggml_free(wc);
    return mismatches;
}

int main() {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    auto env = [](const char * key, const char * value) { need(setenv(key, value, 1) == 0, "environment"); };
    env("GGML_RISCV_QBS", "1");
    env("GGML_RISCV_QBS_EMULATE", "0");
    env("GGML_RISCV_QBS_M4_PREPARE", "1");
    env("GGML_RISCV_QBS_M4_CACHE", "0");
    env("GGML_RISCV_QBS_WIDE_M", "0");
    env("GGML_RISCV_QBS_ACTIVATION_CONTEXT", "0");
    env("GGML_RISCV_QBS_CROSS_OP_CONTEXT", "0");
    env("GGML_RISCV_QBS_TRACE_M4_PREPARE", "1");
    env("GGML_RISCV_QBS_TRACE", "1");
    env("GGML_RISCV_REPACK_TRACE", "1");
    std::printf("M4_STRIDE_CONFIG cache=0 prepare=1 wide_m=0 activation_context=0 emulate=0 threads=1\n");
    std::vector<float> activation(K * 7);
    FILE * file = std::fopen("/activation.bin", "rb");
    need(file, "capture_open");
    need(std::fread(activation.data(), sizeof(float), activation.size(), file) == activation.size(), "capture_prefix");
    need(std::fclose(file) == 0, "capture_close");
    for (float value : activation) need(std::isfinite(value), "finite_capture");
    const auto activation_before = activation;
    unsigned failed = 0, mismatches = 0;
    for (auto type : {GGML_TYPE_Q4_K, GGML_TYPE_Q6_K}) {
        for (int m : {4, 7}) {
            for (int pad : {0, 1, 16}) {
                const unsigned count = run_case(type, m, pad, activation);
                failed += count != 0;
                mismatches += count;
            }
        }
    }
    need(std::memcmp(activation.data(), activation_before.data(), activation.size() * sizeof(float)) == 0,
         "capture_source_integrity");
    std::printf("M4_STRIDE_SUITE_%s graphs=12 matmuls=24 pairs=528 failed_cases=%u mismatches=%u "
                "capture_integrity=1 performance=not_measured\n", failed ? "FAIL" : "PASS", failed, mismatches);
    return failed ? 1 : 0;
}
