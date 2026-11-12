#define main producer_checks_main
#include "target.cpp"
#undef main
#include "q8_K-prepared-reuse.h"

// The production trait is instantiated below; only graph/platform metadata
// and the final command sink are supplied by this single-core layout test.
#define ggml_quantize_mat_q8_K_4x1_ara_generic repack_generic
#include "repack.cpp"
#undef ggml_quantize_mat_q8_K_4x1_ara_generic
extern "C" void frozen_generic(const float *x, void *y, int64_t k) { repack_generic(x, y, k); }

alignas(64) static unsigned char heap[512*1024];
static size_t heap_used;
namespace std { const nothrow_t nothrow; }
void *operator new[](size_t n, const std::nothrow_t &) noexcept {
    n = (n + 63) & ~size_t(63);
    if (n > sizeof(heap) - heap_used) return nullptr;
    void *result = heap + heap_used; heap_used += n; return result;
}
void operator delete[](void *) noexcept {}
void operator delete[](void *, size_t) noexcept {}
void operator delete(void *) noexcept {}
void operator delete(void *, size_t) noexcept {}
extern "C" { struct _reent m8_test_reent{}; struct _reent *_impure_ptr = &m8_test_reent; }
void *__dso_handle;
extern "C" int __cxa_thread_atexit(void (*)(void *), void *, void *) { return 0; }
extern "C" int fprintf(FILE *, const char *, ...) { return 0; }
extern "C" void __cxa_pure_virtual() { test_exit(5); }
ggml::cpu::tensor_traits::~tensor_traits() = default;

static ggml_tensor x{}, weights{}, ops[2]{};
static ggml_tensor *nodes[] = {&ops[0], &ops[1]};
static ggml_cgraph graph{};
static int graph_count = 1, next_chunk, calls4, calls8;
static bool context_reuse, nested_worker, dispatch_second;
static ggml_compute_params outer_params;
static ggml::cpu::tensor_traits *active_trait;
static ggml_tensor *active_op;
static float results[2][64*8];
alignas(64) static unsigned char workspace[8*(K/256)*sizeof(block_q8_K) + 128];
static constexpr size_t Payload = 8*(K/256)*sizeof(block_q8_K);
static unsigned char *wanted4, *wanted8;

extern "C" int ggml_graph_n_nodes(ggml_cgraph *) { return graph_count; }
extern "C" ggml_tensor *ggml_graph_node(ggml_cgraph *, int i) { return nodes[i]; }
extern "C" int64_t ggml_nelements(const ggml_tensor *t) { return t->ne[0]*t->ne[1]*t->ne[2]*t->ne[3]; }
extern "C" int64_t ggml_nrows(const ggml_tensor *t) { return t->ne[1]*t->ne[2]*t->ne[3]; }
extern "C" int ggml_n_dims(const ggml_tensor *t) {
    for (int i = 3; i > 0; --i) if (t->ne[i] != 1) return i + 1;
    return 1;
}
extern "C" bool ggml_is_contiguous(const ggml_tensor *t) {
    size_t stride = 4;
    for (int i = 0; i < 4; ++i) { if (t->nb[i] != stride) return false; stride *= t->ne[i]; }
    return true;
}
extern "C" size_t ggml_nbytes(const ggml_tensor *t) { return size_t(ggml_nelements(t))*4; }
extern "C" int64_t ggml_blck_size(ggml_type type) { return type == GGML_TYPE_F32 ? 1 : 256; }
extern "C" size_t ggml_type_size(ggml_type type) {
    return type == GGML_TYPE_F32 ? 4 : (type == GGML_TYPE_Q4_K ? 144 : 292);
}
extern "C" const char *ggml_type_name(ggml_type) { return "Q4_K"; }
void ggml_log_internal(ggml_log_level, const char *, ...) {}
extern "C" size_t ggml_row_size(ggml_type type, int64_t n) { return n/ggml_blck_size(type)*ggml_type_size(type); }
extern "C" bool ggml_is_numa() { return false; }
extern "C" int64_t ggml_time_us() { return 0; }
static void unused_row_quantizer(const float *, void *, int64_t) { need(false, "unexpected_rowwise_quantizer"); }
extern "C" const ggml_type_traits_cpu *ggml_get_type_traits_cpu(ggml_type) {
    static const ggml_type_traits_cpu value = {unused_row_quantizer, nullptr, GGML_TYPE_Q8_K, 1};
    return &value;
}
void ggml_threadpool_chunk_set(ggml_threadpool *, int n) { next_chunk = n; }
int ggml_threadpool_chunk_add(ggml_threadpool *, int n) { const int old = next_chunk; next_chunk += n; return old; }
void ggml_barrier(ggml_threadpool *) {
    if (dispatch_second && !nested_worker) {
        dispatch_second = false; nested_worker = true;
        auto second = outer_params; second.ith = 1;
        need(active_trait->compute_forward(&second, active_op), "actual_second_worker_forward");
        nested_worker = false;
    }
}

bool ggml_riscv_qbs_supports_tensor(ggml_type type, int64_t k, int64_t n) {
    return type == GGML_TYPE_Q4_K && k == K && n == 64;
}
bool ggml_riscv_qbs_trace_activation_lifetime_enabled() { return false; }
bool ggml_riscv_qbs_prepare_activation_context(const ggml_compute_params *, const ggml_tensor *, ggml_type, int64_t, int64_t) { return context_reuse; }
void ggml_riscv_qbs_trace_activation_lifetime(const void *, const char *, const void *, const char *, ggml_type,
    const void *, const char *, const void *, const void *, size_t, ggml_type, int64_t, int64_t, int64_t,
    uint64_t, bool, uint64_t, bool) {}
int ggml_riscv_qbs_repack_r4(ggml_type, void *, size_t, const void *, size_t, int64_t, int64_t, unsigned) { return 0; }
void ggml_riscv_qbs_mul_mat_view(ggml_type, int, float *, size_t, const void *, const void *, int, int, int64_t, int64_t, unsigned, bool) { need(false, "unexpected_segmented_consumer"); }
void ggml_riscv_qbs_gemv(ggml_type, int, float *, size_t, const void *, const void *, int, int) { need(false, "unexpected_gemv_consumer"); }
void ggml_riscv_qbs_gemm(ggml_type, int, float *, size_t, const void *, const void *a, int rows, int) {
    ++calls4;
    need(rows == 8 && a == workspace + 64 && workspace[64 + Payload] == 0, "m4_consumer_marker");
    need(std::memcmp(a, wanted4, Payload) == 0, "actual_m4_consumer_exact_layout");
}
void ggml_riscv_qbs_gemm_wide(ggml_type, int, float *, size_t, const void *, const void *a, int rows, int) {
    ++calls8;
    need(rows == 8 && a == workspace + 64 && workspace[64 + Payload] == 1, "m8_consumer_marker");
    need(std::memcmp(a, wanted8, Payload) == 0, "actual_m8_consumer_exact_layout");
}
static void shape(ggml_tensor &t, int64_t n, int64_t m, void *data) {
    t.type = GGML_TYPE_F32; t.data = data;
    t.ne[0] = n; t.ne[1] = m; t.ne[2] = t.ne[3] = 1; t.nb[0] = 4;
    for (int i = 1; i < 4; ++i) t.nb[i] = t.nb[i - 1]*t.ne[i - 1];
}
int main() {
    std::memcpy(input, real_attn, 8*K*4);
    for (int row = 0; row < 8; row += 4)
        need(ggml_riscv_q8_K_m4_packed::selected_quantize(input + row*K, m4 + row*(K/256)*292, K), "m4_oracle");
    wanted4 = m4;
    wanted8 = actual + 64;
    need(ggml_riscv_qbs_prepare_m8(input, wanted8, 8, K, 4, K*4), "m8_oracle");
    shape(x, K, 8, input); shape(weights, K, 64, saved);
    weights.type = GGML_TYPE_Q4_K; weights.extra = &weights;
    weights.nb[0] = 144; weights.nb[1] = (K/256)*144; weights.nb[2] = weights.nb[3] = 64*weights.nb[1];
    for (int i = 0; i < 2; ++i) {
        shape(ops[i], 64, 8, results[i]); ops[i].op = GGML_OP_MUL_MAT;
        ops[i].src[0] = &weights; ops[i].src[1] = &x;
    }
    ggml::cpu::repack::tensor_traits<ggml_riscv_qbs_q4_k_tag, 1, 4, GGML_TYPE_Q8_K> trait;
    active_trait = &trait;
    size_t work_bytes = 0;
    need(active_trait->work_size(1, &ops[0], work_bytes) && work_bytes == Payload + 1, "real_trait_work_size_marker_only");
    outer_params.nth = 1; outer_params.cgraph = &graph; outer_params.graph_epoch = 1;
    outer_params.wdata = workspace + 64; outer_params.wsize = work_bytes;
    auto forward = [&](int node, int threads) {
        outer_params.node_index = node; outer_params.nth = threads; outer_params.ith = 0;
        active_op = &ops[node];
        std::memset(workspace, 0xa5, sizeof(workspace));
        if (context_reuse) std::memcpy(workspace + 64, wanted4, Payload);
        state(17, 5);
        need(active_trait->compute_forward(&outer_params, active_op), "real_trait_forward");
        for (size_t i = 0; i < 64; ++i) need(workspace[i] == 0xa5, "workspace_leading_guard");
        for (size_t i = 65 + Payload; i < sizeof(workspace); ++i) need(workspace[i] == 0xa5, "workspace_trailing_guard");
    };
    forward(0, 1);
    need(calls8 == 1 && calls4 == 0, "one_shot_selects_actual_m8_consumer");
    graph_count = 2; ++outer_params.graph_epoch;
    forward(0, 1); forward(1, 1);
    const auto &cache = ggml_riscv_q8_K_prepared::worker_state();
    need(calls8 == 1 && calls4 == 2 && cache.computations == 2 && cache.bytes.statistics().hits == 2,
         "actual_repack_qkv_preserves_cold_warm_cache");
    graph_count = 1; ++outer_params.graph_epoch;
    dispatch_second = true;
    forward(0, 2);
    need(calls8 == 1 && calls4 == 10 && !dispatch_second, "both_actual_workers_consume_m4_layout");
    context_reuse = true; ++outer_params.graph_epoch;
    forward(0, 1);
    need(calls8 == 1 && calls4 == 11 && !generic_calls, "actual_context_reuse_no_requantization");
    test_text("M8_REPACK_LAYOUT_PASS one_shot_m8=1 qkv_m4=2 nth2_workers=2 nth2_m4_chunks=8 context_m4=1 markers_exact=1\n");
    return 0;
}
