// Test-only client of unchanged, frozen GGML and SDK objects.
#include "ggml.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"
#include "repack.h"
#include "arch/riscv/qbs.h"
#include "qbs/qbs.h"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <utility>
#include <vector>

static constexpr int K = 2048, N = 64, KB = 8, Q8 = 292;
static int rows, expected_m, expected_n;
static unsigned info_calls = 0, graph_calls = 0;
static const unsigned char * weight_base;
static const unsigned char * work_base;
static std::vector<unsigned char> workspace;
struct Command {
    unsigned m, n, kb, seed, flags, status;
    size_t weight_offset, activation_offset, stride;
    uint64_t header;
    std::vector<unsigned char> activation, output;
};
static std::vector<Command> commands;

static void need(bool ok, const char * reason) {
    if (!ok) { std::fprintf(stderr, "G4_FAIL reason=%s\n", reason); std::exit(2); }
}
template <typename T> static std::vector<T> read(const char * name, size_t count) {
    std::vector<T> data(count);
    FILE * f = std::fopen(name, "rb");
    need(f && std::fread(data.data(), sizeof(T), count, f) == count && std::fgetc(f) == EOF,
         "input_file_size");
    need(std::fclose(f) == 0, "input_close");
    return data;
}
static void dump(const char * kind, unsigned command, const void * pointer, size_t size) {
    const auto * p = static_cast<const unsigned char *>(pointer);
    for (size_t offset = 0; offset < size; offset += 32) {
        std::printf("G4_BYTES kind=%s command=%u offset=%zu hex=", kind, command, offset);
        for (size_t i = offset; i < size && i < offset+32; ++i) std::printf("%02x", p[i]);
        std::putchar('\n');
    }
}
extern "C" uint64_t __real_qbs_native_info(void *, unsigned);
extern "C" uint64_t __wrap_qbs_native_info(void * p, unsigned index) {
    ++info_calls;
    return __real_qbs_native_info(p, index);
}
extern "C" qbs_status_t __real_qbs_native_execute_command(
    void *, const qbs_descriptor_t *, unsigned, const void *, float *, size_t, unsigned, int);
extern "C" qbs_status_t __wrap_qbs_native_execute_command(
    void * context, const qbs_descriptor_t * descriptor, unsigned m, const void * activation,
    float * output, size_t stride, unsigned n, int segmented) {
    const auto fields = qbs_unpack_descriptor_header(descriptor->header);
    need(m == unsigned(expected_m) && n == unsigned(expected_n) && commands.size() < 4 &&
         !segmented && fields.k_blocks == KB && fields.activation_access == QBS_ACTIVATION_ACCESS_DIRECT,
         "native_command_shape");
    const auto * a = static_cast<const unsigned char *>(activation);
    const auto * w = reinterpret_cast<const unsigned char *>(descriptor->weight_base);
    need(work_base && a >= work_base && a + m*KB*Q8 <= work_base + rows*KB*Q8 &&
         w >= weight_base && w + n*KB*144 <= weight_base + N*KB*144 && stride == N,
         "native_pointer_ranges");
    Command record{};
    record.m = m; record.n = n; record.kb = fields.k_blocks;
    record.weight_offset = w-weight_base; record.activation_offset = a-work_base;
    record.header = descriptor->header; record.stride = stride;
    record.activation.assign(a, a + m*KB*Q8);
    record.output.resize(m*n*4);
    record.seed = commands.size() % 2 ? 8 : 0;
    // Functional flag probes only: do not inherit NX from activation preparation.
    __asm__ volatile("csrw fflags, %0" : : "r"(uint64_t(record.seed)) : "memory");
    const auto status = __real_qbs_native_execute_command(
        context, descriptor, m, activation, output, stride, n, segmented);
    uint64_t flags;
    __asm__ volatile("csrr %0, fflags" : "=r"(flags) : : "memory");
    record.flags = unsigned(flags); record.status = unsigned(status);
    for (unsigned r = 0; r < m; ++r)
        std::memcpy(record.output.data()+r*n*4, output+r*stride, n*4);
    commands.push_back(std::move(record));
    return status;
}
extern "C" ggml_status __real_ggml_graph_compute(ggml_cgraph *, ggml_cplan *);
extern "C" ggml_status __wrap_ggml_graph_compute(ggml_cgraph * graph, ggml_cplan * plan) {
    ++graph_calls;
    need(plan->n_threads == 1 && plan->work_data && plan->work_size >= size_t(rows*KB*Q8),
         "actual_graph_workspace");
    work_base = plan->work_data;
    const auto status = __real_ggml_graph_compute(graph, plan);
    workspace.assign(plan->work_data, plan->work_data + rows*KB*Q8);
    return status;
}

int main(int argc, char ** argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    std::setvbuf(stderr, nullptr, _IONBF, 0);
    need(argc == 2, "arm_argument");
    const bool m8 = !std::strcmp(argv[1], "m8");
    const bool m4 = !std::strcmp(argv[1], "m4");
    const bool shape = !std::strcmp(argv[1], "shape");
    const bool rvv = !std::strcmp(argv[1], "rvv");
    need(m8 || m4 || shape || rvv, "known_arm");
    rows = shape ? 4 : 8;
    expected_m = m8 ? 8 : 4; expected_n = m8 ? 16 : 32;
    auto env = [](const char * key, const char * value) { need(!setenv(key, value, 1), "setenv"); };
    env("GGML_RISCV_QBS", rvv ? "0" : "1");
    env("GGML_RISCV_QBS_EMULATE", "0");
    env("GGML_RISCV_QBS_WIDE_M", m4 ? "0" : "1");
    env("GGML_RISCV_QBS_SEGMENT_K_BLOCKS", "0");
    env("GGML_RISCV_QBS_ACTIVATION_CONTEXT", "0");
    env("GGML_RISCV_QBS_CROSS_OP_CONTEXT", "0");
    env("GGML_RISCV_QBS_TRACE", "1");
    env("GGML_RISCV_QBS_TRACE_CALLS", "1");
    env("GGML_RISCV_QBS_TRACE_LIFETIME", "1");
    env("GGML_RISCV_REPACK_TRACE", "1");
    need(!unsetenv("GGML_RISCV_QBS_FORMATS"), "format_filter");
    __asm__ volatile("csrwi fcsr, 0\ncsrwi vcsr, 0\ncsrwi vstart, 0" : : : "memory");
    if (!rvv) need(qbs_native_info(nullptr, 4) == 0, "QBACC_must_be_unavailable");
    auto input = read<float>("/input.bin", 8*K);
    auto raw = read<unsigned char>("/weight.bin", 128*KB*144);
    const auto input_before = input; const auto raw_before = raw;
    ggml_riscv_qbs_activation_plan selection{};
    if (!rvv) need(ggml_riscv_qbs_plan_activations(GGML_TYPE_Q4_K, rows, N, K, &selection) &&
                   selection.wide_m == m8, "runtime_M8_selection");
    ggml_init_params params{2*1024*1024, nullptr, true};
    auto * wc = ggml_init(params); auto * ctx = ggml_init(params);
    need(wc && ctx, "contexts");
    auto * w = ggml_new_tensor_2d(wc, GGML_TYPE_Q4_K, K, N);
    ggml_set_name(w, "real_qwen3_attn_q_slice");
    need(ggml_riscv_qbs_supports_tensor(w->type, K, N) == !rvv, "tensor_admission");
    auto * wb = ggml_backend_alloc_ctx_tensors_from_buft(wc, ggml_backend_cpu_repack_buffer_type());
    need(wb && w->extra && !std::strcmp(ggml_backend_buffer_name(wb), "CPU_REPACK"), "repack_traits");
    ggml_backend_tensor_set(w, raw.data(), 0, N*KB*144);
    weight_base = static_cast<const unsigned char *>(w->data);
    const auto packed_size = ggml_backend_buffer_get_size(wb);
    const auto * packed = static_cast<const unsigned char *>(ggml_backend_buffer_get_base(wb));
    const std::vector<unsigned char> packed_before(packed, packed+packed_size);
    auto * x = ggml_new_tensor_2d(ctx, GGML_TYPE_F32, K, rows);
    auto * y = ggml_mul_mat(ctx, w, x);
    ggml_set_input(x); ggml_set_output(y);
    auto * graph = ggml_new_graph(ctx); ggml_build_forward_expand(graph, y);
    auto * backend = ggml_backend_cpu_init(); need(backend, "cpu_backend");
    ggml_backend_cpu_set_n_threads(backend, 1);
    auto * buffer = ggml_backend_alloc_ctx_tensors(ctx, backend); need(buffer, "graph_buffer");
    ggml_backend_tensor_set(x, input.data(), 0, rows*K*4);
    commands.reserve(4);
    need(ggml_backend_graph_compute(backend, graph) == GGML_STATUS_SUCCESS, "graph_compute");
    ggml_backend_synchronize(backend);
    std::vector<uint32_t> output(rows*N);
    ggml_backend_tensor_get(y, output.data(), 0, output.size()*4);
    std::vector<float> after(rows*K); ggml_backend_tensor_get(x, after.data(), 0, after.size()*4);
    need(!std::memcmp(after.data(), input.data(), after.size()*4) && input == input_before &&
         raw == raw_before && !std::memcmp(packed, packed_before.data(), packed_size), "input_integrity");
    need(graph_calls == 1 && commands.size() == size_t(rvv ? 0 : shape ? 2 : 4) &&
         (rvv ? info_calls == 0 : info_calls > 0), "complete_native_dispatch");
    std::printf("G4_META arm=%s m=%d n=64 k=2048 wide=%d qbs=%d graph_calls=%u commands=%zu info_calls=%u workspace_bytes=%zu flags_probe=1\n",
        argv[1], rows, int(m8), int(!rvv), graph_calls, commands.size(), info_calls, workspace.size());
    dump("workspace", 0, workspace.data(), workspace.size());
    dump("output", 0, output.data(), output.size()*4);
    for (size_t i = 0; i < commands.size(); ++i) {
        const auto & c = commands[i];
        std::printf("G4_COMMAND id=%zu m=%u n=%u kb=%u woff=%zu aoff=%zu stride=%zu seed=%u flags=%u status=%u header=%016lx\n",
            i, c.m, c.n, c.kb, c.weight_offset, c.activation_offset, c.stride,
            c.seed, c.flags, c.status, c.header);
        dump("activation", unsigned(i), c.activation.data(), c.activation.size());
        dump("command_output", unsigned(i), c.output.data(), c.output.size());
    }
    std::printf("G4_PASS arm=%s outputs=%zu integrity=1 cycles_measured=0\n", argv[1], output.size());
    ggml_backend_buffer_free(buffer); ggml_backend_free(backend);
    ggml_backend_buffer_free(wb); ggml_free(ctx); ggml_free(wc);
    return 0;
}
