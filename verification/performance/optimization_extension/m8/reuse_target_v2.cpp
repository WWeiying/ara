#define main producer_checks_main
#include "target.cpp"
#undef main
#include "q8_K-prepared-reuse.h"

alignas(64) static unsigned char heap[512*1024];
static size_t heap_used;
namespace std { const nothrow_t nothrow; }
void *operator new[](size_t n, const std::nothrow_t &) noexcept {
    n = (n + 63) & ~size_t(63);
    if (n > sizeof(heap) - heap_used) return nullptr;
    void *result = heap + heap_used;
    heap_used += n;
    return result;
}
void operator delete[](void *) noexcept {}
void operator delete[](void *, size_t) noexcept {}
extern "C" {
struct _reent m8_test_reent{};
struct _reent *_impure_ptr = &m8_test_reent;
}
extern "C" int fprintf(FILE *, const char *, ...) { return 0; }

static ggml_tensor x{}, weights{}, ops[2]{};
static ggml_tensor *nodes[] = {&ops[0], &ops[1]};
static ggml_cgraph graph{};
static int graph_count = 2;
static float results[2][64*8];
extern "C" int ggml_graph_n_nodes(ggml_cgraph *) { return graph_count; }
extern "C" ggml_tensor *ggml_graph_node(ggml_cgraph *, int i) { return nodes[i]; }
extern "C" bool ggml_is_contiguous(const ggml_tensor *t) {
    size_t stride = sizeof(float);
    for (unsigned i = 0; i < 4; ++i) { if (t->nb[i] != stride) return false; stride *= t->ne[i]; }
    return true;
}
extern "C" size_t ggml_nbytes(const ggml_tensor *t) {
    return size_t(t->ne[0]*t->ne[1]*t->ne[2]*t->ne[3])*sizeof(float);
}
// Weight-support metadata only; the SDK query, layout planner, reuse policy,
// exact cache, M4 and M8 numerical producers remain the frozen implementations.
bool ggml_riscv_qbs_supports_tensor(ggml_type type, int64_t k, int64_t n) {
    return type == GGML_TYPE_Q4_K && k == K && n == 64;
}
static void shape(ggml_tensor &t, int64_t n, int64_t m, void *data) {
    t.type = GGML_TYPE_F32;
    t.data = data;
    t.ne[0] = n; t.ne[1] = m; t.ne[2] = t.ne[3] = 1;
    t.nb[0] = sizeof(float);
    for (unsigned i = 1; i < 4; ++i) t.nb[i] = t.nb[i - 1]*t.ne[i - 1];
}

int main() {
    std::memcpy(input, real_attn, 8*K*sizeof(float));
    shape(x, K, 8, input);
    shape(weights, K, 64, nullptr);
    weights.type = GGML_TYPE_Q4_K; weights.extra = &weights;
    for (int i = 0; i < 2; ++i) {
        shape(ops[i], 64, 8, results[i]);
        ops[i].op = GGML_OP_MUL_MAT; ops[i].src[0] = &weights; ops[i].src[1] = &x;
    }
    ggml_compute_params params{};
    params.nth = 1; params.graph_epoch = 1; params.cgraph = &graph;
    ggml_riscv_q8_K_prepared::state cache;
    ggml_riscv_qbs_activation_plan plan{};
    need(ggml_riscv_qbs_plan_activations(GGML_TYPE_Q4_K, 8, 64, K, &plan) && plan.direct_m8, "singleton_shape_candidate");
    need(ggml_riscv_q8_K_prepared::supported(&ops[0]), "m4_support_independent_of_auto_m8");

    std::memset(expected, 0xa5, sizeof(expected));
    state(0, 5);
    for (int row = 0; row < 8; row += 4) {
        need(ggml_riscv_q8_K_m4_packed::selected_quantize(input + row*K,
            expected + 64 + size_t(row)*(K/256)*sizeof(block_q8_K), K), "m4_selected_oracle");
    }
    const unsigned raised = fcsr() & 31;
    for (int node = 0; node < 2; ++node) {
        params.node_index = node;
        const auto policy = cache.begin(&params, &ops[node]);
        need(policy.lookup && policy.fill == (node == 0), "real_qkv_reuse_policy");
        std::memset(actual, 0xa5, sizeof(actual)); state(17, 5);
        need(!ggml_riscv_qbs_prepare_m8(input, actual + 64, 8, K, 4, K*4, params.nth, policy.lookup, false), "m4_lookup_vetoes_m8");
        need(untouched() && fcsr() == 17 && vcsr() == 5 && !generic_calls, "lookup_veto_no_work");
        for (int group = 0; group < 2; ++group) {
            need(cache.prepare(policy, input + group*4*K,
                actual + 64 + group*4*(K/256)*sizeof(block_q8_K), K, group, false), "m4_cache_produced");
        }
        need(std::memcmp(expected, actual, sizeof(actual)) == 0, "m4_cold_warm_payload_and_guards");
        need(fcsr() == (17 | raised) && vcsr() == 5 && !vstart(), "m4_cold_warm_csr");
        if (node == 0) need(cache.computations == 2 && cache.bytes.statistics().stores == 2, "two_cold_m4_groups");
        else need(cache.computations == 2 && cache.bytes.statistics().hits == 2, "warm_no_requantization");
        cache.finish(policy);
    }
    graph_count = 1; params.node_index = 0;
    const auto singleton = cache.begin(&params, &ops[0]);
    need(!singleton.lookup, "one_shot_no_lookup");
    std::memset(actual, 0xa5, sizeof(actual)); state(17, 5);
    need(ggml_riscv_qbs_prepare_m8(input, actual + 64, 8, K, 4, K*4, 1, singleton.lookup, false), "one_shot_m8_admitted");
    std::memset(actual, 0xa5, sizeof(actual)); state(17, 5);
    need(!ggml_riscv_qbs_prepare_m8(input, actual + 64, 8, K, 4, K*4, 1, false, true), "context_reuse_vetoes_m8");
    need(untouched() && fcsr() == 17 && vcsr() == 5, "context_no_requantization");
    params.nth = 2;
    need(!cache.begin(&params, &ops[0]).lookup, "multithread_no_m4_cache_lookup");
    need(!ggml_riscv_qbs_prepare_m8(input, actual + 64, 8, K, 4, K*4, 2), "multithread_no_auto_m8");
    need(untouched() && fcsr() == 17 && vcsr() == 5 && !generic_calls, "multithread_no_m8_work");
    test_text("M8_REUSE_PRIORITY_PASS computations=2 hits=2 one_shot=1 context_reuse_veto=1 nth2_veto=1\n");
    return 0;
}
