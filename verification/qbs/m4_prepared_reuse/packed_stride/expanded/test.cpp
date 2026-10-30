#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"
#include "ggml-quants.h"
#include "repack.h"
#include "arch/riscv/qbs.h"
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <sys/wait.h>
#include <unistd.h>

static constexpr int N = 8, GUARD = 16, CAPTURE_K = 1536, CAPTURE_M = 15;
static int case_id = -1;
static void need(bool ok, const char * reason) {
    if (!ok) {
        std::printf("XS_ERROR id=%d reason=%s\n", case_id, reason);
        std::exit(2);
    }
}
static uint32_t bits(float value) {
    uint32_t result;
    std::memcpy(&result, &value, sizeof(result));
    return result;
}
struct Observation {
    int k, m, element, pad;
    ggml_tensor * weights;
    ggml_tensor * backing[2];
    ggml_tensor * inputs[2];
    ggml_tensor * outputs[2];
    void * addresses[2];
    unsigned before[2] = {}, after[2] = {};
};
static bool observe(ggml_tensor * node, bool ask, void * opaque) {
    auto & o = *static_cast<Observation *>(opaque);
    need(node->op == GGML_OP_VIEW || node->op == GGML_OP_PERMUTE || node->op == GGML_OP_MUL_MAT,
         "scheduler_added_operation");
    if (node->op != GGML_OP_MUL_MAT) return false;
    const int side = node == o.outputs[0] ? 0 : 1;
    need(node == o.outputs[side] && node->src[0] == o.weights, "scheduled_weights_or_output");
    auto * x = node->src[1];
    const size_t element = side ? o.element : 4;
    const size_t row = o.k * element + (side ? o.pad * 4 : 0);
    need(x == o.inputs[side] && x->data == o.addresses[side], "scheduler_replaced_input");
    need(x->view_src == o.backing[side] &&
         x->data == static_cast<char *>(o.backing[side]->data) + GUARD * 4, "backing_identity");
    need(x->nb[0] == element && x->nb[1] == row && x->ne[0] == o.k && x->ne[1] == o.m &&
         x->ne[2] == 1 && x->ne[3] == 1, "scheduled_shape_stride");
    need(x->op == (element == 8 ? GGML_OP_PERMUTE : GGML_OP_VIEW), "legal_view_operation");
    (ask ? o.before[side] : o.after[side])++;
    std::printf("XS_OBSERVE id=%d side=%d phase=%s nb0=%zu nb1=%zu contiguous=%d "
                "op=%s same_tensor=1 same_data=1 same_backing=1\n", case_id, side,
                ask ? "before" : "after", x->nb[0], x->nb[1], int(ggml_is_contiguous(x)),
                element == 8 ? "PERMUTE" : "VIEW");
    return true;
}
static int run_case(const char * name, int k, int m, int element, int pad, int wide, int threads) {
    ggml_type type = GGML_TYPE_COUNT;
    if (!std::strcmp(name, "Q4_K")) type = GGML_TYPE_Q4_K;
    if (!std::strcmp(name, "Q6_K")) type = GGML_TYPE_Q6_K;
    if (!std::strcmp(name, "Q4_0")) type = GGML_TYPE_Q4_0;
    if (!std::strcmp(name, "Q8_0")) type = GGML_TYPE_Q8_0;
    need(type != GGML_TYPE_COUNT && (k == 512 || k == 1536) && m >= 1 && m <= 15 &&
         (element == 4 || element == 8) && pad > 0 && pad <= 16 &&
         (wide == 0 || wide == 1) && (threads == 1 || threads == 2), "case_arguments");
    auto env = [](const char * key, const char * value) { need(setenv(key, value, 1) == 0, "environment"); };
    env("GGML_RISCV_QBS", "1");
    env("GGML_RISCV_QBS_EMULATE", "0");
    env("GGML_RISCV_QBS_M4_PREPARE", "1");
    env("GGML_RISCV_QBS_M4_CACHE", "0");
    env("GGML_RISCV_QBS_WIDE_M", wide ? "1" : "0");
    env("GGML_RISCV_QBS_ACTIVATION_CONTEXT", "0");
    env("GGML_RISCV_QBS_CROSS_OP_CONTEXT", "0");
    env("GGML_RISCV_QBS_SEGMENT_K_BLOCKS", "0");
    env("GGML_RISCV_QBS_TRACE_M4_PREPARE", "1");
    env("GGML_RISCV_QBS_TRACE", "1");
    env("GGML_RISCV_QBS_TRACE_CALLS", "1");
    env("GGML_RISCV_REPACK_TRACE", "1");
    need(unsetenv("GGML_RISCV_QBS_FORMATS") == 0, "format_filter");
    std::printf("XS_BEGIN id=%d type=%s k=%d n=%d m=%d element=%d pad=%d wide=%d threads=%d "
                "cache=0 prepare=1 context=0 emulate=0 segment=0 capture_row_k=1536\n",
                case_id, name, k, N, m, element, pad, wide, threads);
    ggml_riscv_qbs_activation_plan plan{};
    need(ggml_riscv_qbs_plan_activations(type, m, N, k, &plan), "activation_plan");
    need(plan.wide_m == bool(wide && m >= 8), "wide_selection");
    std::printf("XS_PLAN id=%d wide=%d row_major_bytes=%zu packed_bytes=%zu workspace_bytes=%zu\n",
                case_id, int(plan.wide_m), plan.row_major_bytes, plan.packed_bytes, plan.workspace_bytes);
    std::vector<float> capture(CAPTURE_K * CAPTURE_M);
    FILE * file = std::fopen("/activation.bin", "rb");
    need(file, "capture_open");
    need(std::fread(capture.data(), sizeof(float), capture.size(), file) == capture.size() &&
         std::fgetc(file) == EOF, "capture_size");
    need(std::fclose(file) == 0, "capture_close");
    for (float value : capture) need(std::isfinite(value), "finite_capture");
    const auto capture_before = capture;
    ggml_init_params params{2 * 1024 * 1024, nullptr, true};
    auto * wc = ggml_init(params);
    auto * ctx = ggml_init(params);
    need(wc && ctx, "contexts");
    auto * w = ggml_new_tensor_2d(wc, type, k, N);
    auto * wb = ggml_backend_alloc_ctx_tensors_from_buft(wc, ggml_backend_cpu_repack_buffer_type());
    need(wb && w->extra && !std::strcmp(ggml_backend_buffer_name(wb), "CPU_REPACK"), "repacked_weights");
    ggml_backend_buffer_clear(wb, 0xa5);
    std::vector<float> weights(k * N);
    for (int i = 0; i < k * N; ++i) weights[i] = float((i * 17 + (i / k) * 3) % 127 - 63) / 512;
    const auto weights_before = weights;
    std::vector<unsigned char> raw(ggml_row_size(type, k) * N);
    switch (type) {
        case GGML_TYPE_Q4_K: quantize_row_q4_K_ref(weights.data(), reinterpret_cast<block_q4_K *>(raw.data()), k*N); break;
        case GGML_TYPE_Q6_K: quantize_row_q6_K_ref(weights.data(), reinterpret_cast<block_q6_K *>(raw.data()), k*N); break;
        case GGML_TYPE_Q4_0: quantize_row_q4_0_ref(weights.data(), reinterpret_cast<block_q4_0 *>(raw.data()), k*N); break;
        case GGML_TYPE_Q8_0: quantize_row_q8_0_ref(weights.data(), reinterpret_cast<block_q8_0 *>(raw.data()), k*N); break;
        default: need(false, "weight_type");
    }
    const auto raw_before = raw;
    ggml_backend_tensor_set(w, raw.data(), 0, raw.size());
    const auto * packed = static_cast<const unsigned char *>(ggml_backend_buffer_get_base(wb));
    const size_t packed_size = ggml_backend_buffer_get_size(wb);
    const std::vector<unsigned char> packed_before(packed, packed + packed_size);
    void * const weight_extra = w->extra;
    void * const weight_data = w->data;
    auto * backend = ggml_backend_cpu_init();
    need(backend, "backend");
    ggml_backend_cpu_set_n_threads(backend, threads);
    ggml_tensor * backing[2], * x[2], * y[2];
    std::vector<float> storage[2];
    auto * graph = ggml_new_graph(ctx);
    for (int side = 0; side < 2; ++side) {
        const int step = side ? element / 4 : 1;
        const int stride = k * step + (side ? pad : 0);
        storage[side].resize(GUARD + m * stride + GUARD);
        for (size_t i = 0; i < storage[side].size(); ++i) storage[side][i] = 19.0f + float(i % 31) / 8;
        for (int row = 0; row < m; ++row) {
            for (int col = 0; col < k; ++col) {
                storage[side][GUARD + row * stride + col * step] = capture[row * CAPTURE_K + col];
            }
        }
        backing[side] = ggml_new_tensor_1d(ctx, GGML_TYPE_F32, storage[side].size());
        ggml_set_input(backing[side]);
        if (step == 1) {
            x[side] = ggml_view_2d(ctx, backing[side], k, m, stride * 4, GUARD * 4);
        } else {
            // Move the singleton unit-stride dimension out of the logical K/M axes.
            auto * view = ggml_view_3d(ctx, backing[side], 1, k, m, step * 4, stride * 4, GUARD * 4);
            x[side] = ggml_permute(ctx, view, 2, 0, 1, 3);
        }
        y[side] = ggml_mul_mat(ctx, w, x[side]);
        ggml_set_output(y[side]);
        ggml_build_forward_expand(graph, y[side]);
    }
    auto * buffer = ggml_backend_alloc_ctx_tensors(ctx, backend);
    need(buffer, "activation_buffer");
    const std::vector<uint32_t> unwritten(N * m, UINT32_C(0x7fc00001));
    for (int side = 0; side < 2; ++side) {
        ggml_backend_tensor_set(backing[side], storage[side].data(), 0, storage[side].size() * 4);
        ggml_backend_tensor_set(y[side], unwritten.data(), 0, unwritten.size() * 4);
        need(ggml_backend_supports_op(backend, y[side]), "backend_rejects_view");
        for (int row = 0; row < m; ++row) {
            for (int col = 0; col < k; ++col) {
                need(!std::memcmp(static_cast<char *>(x[side]->data) + row*x[side]->nb[1] + col*x[side]->nb[0],
                                  &capture[row*CAPTURE_K + col], 4), "paired_input_bits");
            }
        }
    }
    Observation observation{k, m, element, pad, w, {backing[0], backing[1]}, {x[0], x[1]},
                            {y[0], y[1]}, {x[0]->data, x[1]->data}};
    auto * sched = ggml_backend_sched_new(&backend, nullptr, 1, GGML_DEFAULT_GRAPH_SIZE, false, false);
    need(sched, "scheduler");
    ggml_backend_sched_set_eval_callback(sched, observe, &observation);
    need(ggml_backend_sched_alloc_graph(sched, graph), "scheduler_allocation");
    const auto status = ggml_backend_sched_graph_compute(sched, graph);
    need(status == GGML_STATUS_SUCCESS, "complete_graph_status");
    for (int side = 0; side < 2; ++side) {
        need(observation.before[side] == 1 && observation.after[side] == 1, "complete_callbacks");
        std::vector<float> after(storage[side].size());
        ggml_backend_tensor_get(backing[side], after.data(), 0, after.size() * 4);
        need(!std::memcmp(after.data(), storage[side].data(), after.size() * 4), "backing_integrity");
    }
    need(w->extra == weight_extra && w->data == weight_data &&
         !std::memcmp(packed, packed_before.data(), packed_size), "packed_weight_integrity");
    need(raw == raw_before && !std::memcmp(weights.data(), weights_before.data(), weights.size() * 4), "weight_source_integrity");
    need(!std::memcmp(capture.data(), capture_before.data(), capture.size() * 4), "capture_integrity");
    std::vector<float> result[2] = {std::vector<float>(N*m), std::vector<float>(N*m)};
    for (int side = 0; side < 2; ++side) ggml_backend_tensor_get(y[side], result[side].data(), 0, N*m*4);
    unsigned mismatches = 0;
    for (int i = 0; i < N*m; ++i) {
        const float ref = result[0][i], got = result[1][i];
        need(std::isfinite(ref) && std::isfinite(got), "finite_complete_outputs");
        std::printf("XS_VALUE id=%d index=%d row=%d col=%d ref=%.9g got=%.9g ref_bits=%08x got_bits=%08x\n",
                    case_id, i, i/N, i%N, double(ref), double(got), bits(ref), bits(got));
        if (bits(ref) != bits(got)) {
            if (!mismatches) std::printf("XS_FIRST_MISMATCH id=%d index=%d row=%d col=%d ref_bits=%08x got_bits=%08x\n",
                                        case_id, i, i/N, i%N, bits(ref), bits(got));
            ++mismatches;
        }
    }
    std::printf("XS_CASE id=%d outputs=%d mismatches=%u graph_status=%d complete=1 finite=1 "
                "paired_inputs=1 backing_integrity=1 weight_integrity=1 capture_integrity=1 result=%s\n",
                case_id, N*m, mismatches, int(status), mismatches ? "FAIL" : "PASS");
    ggml_backend_sched_free(sched);
    ggml_backend_buffer_free(buffer);
    ggml_backend_free(backend);
    ggml_backend_buffer_free(wb);
    ggml_free(ctx);
    ggml_free(wc);
    return mismatches ? 1 : 0;
}
int main(int argc, char ** argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    std::setvbuf(stderr, nullptr, _IONBF, 0);
    if (argc == 10) {
        case_id = std::atoi(argv[1]);
        return run_case(argv[2], std::atoi(argv[3]), std::atoi(argv[4]), std::atoi(argv[5]),
                        std::atoi(argv[6]), std::atoi(argv[7]), std::atoi(argv[8]));
    }
    need(argc == 1, "usage");
    FILE * cases = std::fopen("/cases.txt", "r");
    need(cases, "cases_open");
    int id, k, m, element, pad, wide, threads, completed = 0, outputs = 0;
    char type[16];
    while (std::fscanf(cases, "%d %15s %d %d %d %d %d %d", &id, type, &k, &m, &element, &pad, &wide, &threads) == 8) {
        std::printf("XS_PROCESS_BEGIN id=%d\n", id);
        const pid_t pid = fork();
        need(pid >= 0, "fork");
        if (pid == 0) {
            std::vector<std::string> args{"/test", std::to_string(id), type, std::to_string(k), std::to_string(m),
                std::to_string(element), std::to_string(pad), std::to_string(wide), std::to_string(threads), "child"};
            std::vector<char *> pointers;
            for (auto & arg : args) pointers.push_back(arg.data());
            pointers.push_back(nullptr);
            execv("/test", pointers.data());
            _exit(127);
        }
        int status = 0;
        need(waitpid(pid, &status, 0) == pid, "waitpid");
        const int rc = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
        std::printf("XS_PROCESS_END id=%d rc=%d\n", id, rc);
        if (rc) return rc;
        ++completed;
        outputs += N*m;
    }
    need(std::feof(cases) && std::fclose(cases) == 0, "cases_complete");
    std::printf("XS_SHARD_PASS cases=%d matmuls=%d pairs=%d performance=not_measured\n", completed, 2*completed, outputs);
    return 0;
}
