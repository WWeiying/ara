#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"
#include "repack.h"
#include "arch/riscv/qbs.h"
#include <riscv_vector.h>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static constexpr int K = 512, N = 32, GUARD = 16, CAPTURE_K = 1536, CAPTURE_M = 15;
static int case_id = -1;
static void need(bool ok, const char *reason) {
    if (!ok) {
        std::printf("RF_ERROR id=%d reason=%s\n", case_id, reason);
        std::exit(2);
    }
}
static uint32_t bits(float value) {
    uint32_t word;
    std::memcpy(&word, &value, 4);
    return word;
}
template <typename T> static std::vector<T> read(const char *path, size_t count) {
    std::vector<T> values(count);
    FILE *file = std::fopen(path, "rb");
    need(file, "capture_open");
    need(std::fread(values.data(), sizeof(T), count, file) == count && std::fgetc(file) == EOF, "capture_size");
    need(std::fclose(file) == 0, "capture_close");
    return values;
}
struct Observation {
    int m, element, pad;
    ggml_tensor *weights;
    ggml_tensor *backing[3], *inputs[3], *outputs[3];
    void *addresses[3];
    unsigned before[3] = {}, after[3] = {};
};
static bool observe(ggml_tensor *node, bool ask, void *opaque) {
    auto &o = *static_cast<Observation *>(opaque);
    need(node->op == GGML_OP_VIEW || node->op == GGML_OP_PERMUTE || node->op == GGML_OP_MUL_MAT,
         "unexpected_scheduler_operation");
    if (node->op != GGML_OP_MUL_MAT) return false;
    int side = 0;
    while (side < 3 && node != o.outputs[side]) ++side;
    need(side < 3 && node->src[0] == o.weights, "scheduled_weight_or_output");
    auto *x = node->src[1];
    const size_t element = side == 2 ? o.element : 4;
    const size_t row = K*element + (side == 2 ? o.pad*4 : 0);
    need(x == o.inputs[side] && x->data == o.addresses[side], "scheduler_replaced_input");
    need(x->view_src == o.backing[side] &&
         x->data == static_cast<char *>(o.backing[side]->data) + GUARD*4, "backing_identity");
    need(x->nb[0] == element && x->nb[1] == row && x->ne[0] == K && x->ne[1] == o.m &&
         x->ne[2] == 1 && x->ne[3] == 1, "scheduled_geometry");
    need(x->op == (element == 8 ? GGML_OP_PERMUTE : GGML_OP_VIEW), "legal_view_operation");
    (ask ? o.before[side] : o.after[side])++;
    std::printf("RF_OBSERVE id=%d side=%d phase=%s nb0=%zu nb1=%zu contiguous=%d op=%s "
                "same_tensor=1 same_data=1 same_backing=1\n", case_id, side,
                ask ? "before" : "after", x->nb[0], x->nb[1], int(ggml_is_contiguous(x)),
                element == 8 ? "PERMUTE" : "VIEW");
    return true;
}
static bool run_case(int m, int element, int pad) {
    std::printf("RF_BEGIN id=%d type=Q4_K k=%d n=%d m=%d element=%d pad=%d\n", case_id, K, N, m, element, pad);
    auto capture = read<float>("/activation.bin", CAPTURE_K*CAPTURE_M);
    for (float value : capture) need(std::isfinite(value), "finite_capture");
    const auto capture_before = capture;
    const size_t captured_row_bytes = ggml_row_size(GGML_TYPE_Q4_K, CAPTURE_K);
    auto weights = read<unsigned char>("/weights.bin", captured_row_bytes*1536);
    const auto weights_before = weights;
    const size_t row_bytes = ggml_row_size(GGML_TYPE_Q4_K, K);
    std::vector<unsigned char> raw(N*row_bytes);
    for (int row = 0; row < N; ++row)
        std::memcpy(raw.data() + row*row_bytes, weights.data() + row*captured_row_bytes, row_bytes);
    const auto raw_before = raw;

    ggml_init_params params{2*1024*1024, nullptr, true};
    auto *wc = ggml_init(params);
    auto *ctx = ggml_init(params);
    need(wc && ctx, "contexts");
    auto *w = ggml_new_tensor_2d(wc, GGML_TYPE_Q4_K, K, N);
    ggml_set_name(w, "rvv_q4k");
    need(!ggml_riscv_qbs_supports_tensor(w->type, K, N), "qbs_unexpectedly_supported");
    auto *wb = ggml_backend_alloc_ctx_tensors_from_buft(wc, ggml_backend_cpu_repack_buffer_type());
    need(wb && w->extra && !std::strcmp(ggml_backend_buffer_name(wb), "CPU_REPACK"), "ordinary_repack_buffer");
    need(w->buffer == wb, "weight_buffer_ownership");
    ggml_backend_buffer_clear(wb, 0xa5);
    ggml_backend_tensor_set(w, raw.data(), 0, raw.size());
    const auto *packed = static_cast<const unsigned char *>(ggml_backend_buffer_get_base(wb));
    const size_t packed_size = ggml_backend_buffer_get_size(wb);
    const std::vector<unsigned char> packed_before(packed, packed + packed_size);
    void *const weight_extra = w->extra;
    void *const weight_data = w->data;
    std::printf("RF_WEIGHT id=%d buffer=CPU_REPACK qbs_supported=0 owned=1 extra=%p data=%p captured=1\n",
                case_id, weight_extra, weight_data);
    auto *backend = ggml_backend_cpu_init();
    need(backend, "backend");
    ggml_backend_cpu_set_n_threads(backend, 1);
    ggml_tensor *backing[3], *x[3], *y[3];
    std::vector<float> storage[3];
    auto *graph = ggml_new_graph(ctx);
    for (int side = 0; side < 3; ++side) {
        const int step = side == 2 ? element/4 : 1;
        const int stride = K*step + (side == 2 ? pad : 0);
        storage[side].resize(GUARD + m*stride + GUARD);
        for (size_t i = 0; i < storage[side].size(); ++i) storage[side][i] = 19.0f + float(i%31)/8;
        for (int row = 0; row < m; ++row)
            for (int col = 0; col < K; ++col)
                storage[side][GUARD + row*stride + col*step] = capture[row*CAPTURE_K + col];
        backing[side] = ggml_new_tensor_1d(ctx, GGML_TYPE_F32, storage[side].size());
        ggml_set_input(backing[side]);
        if (step == 1) {
            x[side] = ggml_view_2d(ctx, backing[side], K, m, stride*4, GUARD*4);
        } else {
            auto *view = ggml_view_3d(ctx, backing[side], 1, K, m, step*4, stride*4, GUARD*4);
            x[side] = ggml_permute(ctx, view, 2, 0, 1, 3);
        }
        y[side] = ggml_mul_mat(ctx, w, x[side]);
        ggml_set_output(y[side]);
        ggml_build_forward_expand(graph, y[side]);
    }
    auto *buffer = ggml_backend_alloc_ctx_tensors(ctx, backend);
    need(buffer, "activation_buffer");
    const std::vector<uint32_t> unwritten(N*m, UINT32_C(0x7fc00001));
    for (int side = 0; side < 3; ++side) {
        ggml_backend_tensor_set(backing[side], storage[side].data(), 0, storage[side].size()*4);
        ggml_backend_tensor_set(y[side], unwritten.data(), 0, unwritten.size()*4);
        need(ggml_backend_supports_op(backend, y[side]), "backend_rejects_view");
        for (int row = 0; row < m; ++row)
            for (int col = 0; col < K; ++col)
                need(!std::memcmp(static_cast<char *>(x[side]->data) + row*x[side]->nb[1] + col*x[side]->nb[0],
                                  &capture[row*CAPTURE_K + col], 4), "paired_input_bits");
    }
    Observation observation{m, element, pad, w, {backing[0], backing[1], backing[2]},
        {x[0], x[1], x[2]}, {y[0], y[1], y[2]}, {x[0]->data, x[1]->data, x[2]->data}};
    auto *sched = ggml_backend_sched_new(&backend, nullptr, 1, GGML_DEFAULT_GRAPH_SIZE, false, false);
    need(sched, "scheduler");
    ggml_backend_sched_set_eval_callback(sched, observe, &observation);
    need(ggml_backend_sched_alloc_graph(sched, graph), "scheduler_allocation");
    const auto status = ggml_backend_sched_graph_compute(sched, graph);
    need(status == GGML_STATUS_SUCCESS, "graph_status");
    std::vector<float> result[3] = {std::vector<float>(N*m), std::vector<float>(N*m), std::vector<float>(N*m)};
    for (int side = 0; side < 3; ++side) {
        need(observation.before[side] == 1 && observation.after[side] == 1, "complete_callbacks");
        std::vector<float> after(storage[side].size());
        ggml_backend_tensor_get(backing[side], after.data(), 0, after.size()*4);
        need(!std::memcmp(after.data(), storage[side].data(), after.size()*4), "backing_integrity");
        ggml_backend_tensor_get(y[side], result[side].data(), 0, N*m*4);
    }
    need(w->extra == weight_extra && w->data == weight_data && w->buffer == wb &&
         !std::memcmp(packed, packed_before.data(), packed_size), "packed_weight_integrity");
    need(raw == raw_before && weights == weights_before &&
         !std::memcmp(capture.data(), capture_before.data(), capture.size()*4), "capture_integrity");
    unsigned mismatches = 0, control_mismatches = 0;
    std::vector<unsigned> row_mismatches(m);
    for (int i = 0; i < N*m; ++i) {
        const float ref = result[0][i], control = result[1][i], got = result[2][i];
        need(std::isfinite(ref) && std::isfinite(control) && std::isfinite(got), "finite_complete_outputs");
        std::printf("RF_VALUE id=%d index=%d row=%d col=%d ref=%.9g control=%.9g got=%.9g "
                    "ref_bits=%08x control_bits=%08x got_bits=%08x\n", case_id, i, i/N, i%N,
                    double(ref), double(control), double(got), bits(ref), bits(control), bits(got));
        control_mismatches += bits(ref) != bits(control);
        if (bits(ref) != bits(got)) {
            if (!mismatches) std::printf("RF_FIRST id=%d index=%d row=%d col=%d ref_bits=%08x got_bits=%08x\n",
                                        case_id, i, i/N, i%N, bits(ref), bits(got));
            ++mismatches;
            ++row_mismatches[i/N];
        }
    }
    for (int row = 0; row < m; ++row)
        std::printf("RF_ROW id=%d row=%d mismatches=%u outputs=%d\n", case_id, row, row_mismatches[row], N);
    std::printf("RF_CASE id=%d outputs=%d mismatches=%u control_mismatches=%u graph_status=%d "
                "complete=1 finite=1 paired_inputs=1 backing_integrity=1 weight_integrity=1 capture_integrity=1 result=%s\n",
                case_id, N*m, mismatches, control_mismatches, int(status),
                mismatches || control_mismatches ? "FAIL" : "PASS");
    ggml_backend_sched_free(sched);
    ggml_backend_buffer_free(buffer);
    ggml_backend_free(backend);
    ggml_backend_buffer_free(wb);
    ggml_free(ctx);
    ggml_free(wc);
    need(control_mismatches == 0, "dense_repeat_control");
    return mismatches != 0;
}
int main() {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    std::setvbuf(stderr, nullptr, _IONBF, 0);
    for (const char *key : {"GGML_RISCV_QBS", "GGML_RISCV_QBS_EMULATE", "GGML_RISCV_QBS_M4_PREPARE",
                           "GGML_RISCV_QBS_M4_PACKED", "GGML_RISCV_QBS_M4_CACHE", "GGML_RISCV_QBS_WIDE_M",
                           "GGML_RISCV_QBS_ACTIVATION_CONTEXT", "GGML_RISCV_QBS_CROSS_OP_CONTEXT",
                           "GGML_RISCV_QBS_SEGMENT_K_BLOCKS"}) need(setenv(key, "0", 1) == 0, "disable_qbs");
    for (const char *key : {"GGML_RISCV_REPACK_TRACE", "GGML_RISCV_QBS_TRACE", "GGML_RISCV_QBS_TRACE_CALLS",
                           "GGML_RISCV_QBS_TRACE_TENSORS", "GGML_RISCV_QBS_TRACE_M4_PREPARE"})
        need(setenv(key, "1", 1) == 0, "enable_trace");
    need(unsetenv("GGML_RISCV_QBS_FORMATS") == 0, "format_filter");
    const size_t vlen = __riscv_vlenb()*8, vl = __riscv_vsetvl_e32m1(32);
    need(vlen == 1024 && vl == 32, "rvv_geometry");
    std::printf("RF_CONFIG qbs=0 emulate=0 prepare=0 packed=0 cache=0 context=0 wide=0 threads=1 vlen=%zu vl32=%zu\n", vlen, vl);
    const int matrix[4][3] = {{4, 4, 16}, {7, 4, 16}, {4, 8, 3}, {7, 8, 3}};
    for (case_id = 0; case_id < 4; ++case_id) {
        if (run_case(matrix[case_id][0], matrix[case_id][1], matrix[case_id][2])) {
            std::printf("RF_STOP reason=first_mismatch planned=4 completed=%d skipped=%d performance=not_measured\n", case_id+1, 3-case_id);
            return 1;
        }
    }
    std::printf("RF_STOP reason=not_reproduced planned=4 completed=4 skipped=0 performance=not_measured\n");
    return 0;
}
