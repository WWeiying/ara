#include "q8_K-prepared-reuse.h"
#include <new>
#include <type_traits>

#define NI __attribute__((no_instrument_function))
extern "C" const unsigned adapter_case, adapter_k, adapter_gate;
extern "C" const float adapter_input[];
extern "C" void frozen_generic(const float *, void *, int64_t);
extern "C" void test_text(const char *);
extern "C" void test_number(uint64_t);
extern "C" void test_exit(unsigned) __attribute__((noreturn));

static constexpr size_t MaxK = 4096, MaxFloats = 4 * MaxK;
static constexpr size_t MaxBytes = MaxK / 256 * sizeof(block_q8_Kx4);
static_assert(sizeof(block_q8_Kx4) == 1168, "accepted M4 layout");
alignas(64) static float input[MaxFloats], saved[MaxFloats];
alignas(64) static unsigned char expected[MaxBytes + 128], actual[MaxBytes + 128];
alignas(64) static unsigned char heap[512 * 1024];
static size_t used, watched_bytes;
static unsigned generic_calls, candidate_calls, planner_calls, checks;
static unsigned abort_candidates, abort_generics;
static uint64_t abort_queries;
static void *watched_output;
static ggml_riscv_q8_K_prepared::state *watched_cache;
static ggml_tensor x{}, w{}, ops[2]{};
static ggml_tensor *nodes[2] = {&ops[0], &ops[1]};
static ggml_cgraph graph{};
static unsigned graph_count = 2;
static float results[2][8 * 64];

static unsigned NI fc() { unsigned v; asm volatile("frcsr %0" : "=r"(v) :: "memory"); return v; }
static unsigned NI vc() { unsigned v; asm volatile("csrr %0,vcsr" : "=r"(v) :: "memory"); return v; }
static unsigned NI vs() { unsigned v; asm volatile("csrr %0,vstart" : "=r"(v) :: "memory"); return v; }
static void NI controls(unsigned f, unsigned v) {
    asm volatile("csrw fcsr,%0;csrw vcsr,%1;csrwi vstart,0" :: "r"(f), "r"(v) : "memory");
}
static void NI need(bool ok, const char *why) {
    ++checks;
    if (!ok) { test_text("M4_ADAPTER_FAIL reason="); test_text(why); test_text("\n"); test_exit(1); }
}
static bool NI untouched() {
    const auto *p = static_cast<const unsigned char *>(watched_output);
    for (size_t i = 0; i < watched_bytes; ++i) if (p[i] != 0xa5) return false;
    return true;
}
static bool NI actual_untouched() {
    for (size_t i = 0; i < sizeof(actual); ++i) if (actual[i] != 0xa5) return false;
    return true;
}
static void NI field(const char *name, uint64_t value) { test_text(name); test_number(value); }

extern "C" void NI __cyg_profile_func_enter(void *fn, void *) {
#ifdef GGML_USE_RISCV_QBS_M4_PREFLIGHT
    if (fn == reinterpret_cast<void *>(&qbs_experimental_m4_preflight::quantize)) ++candidate_calls;
#else
    (void) fn;
#endif
}
extern "C" void NI __cyg_profile_func_exit(void *, void *) {}

// The harness supplies metadata/environment only. Producers and cache are real headers.
extern "C" char *NI getenv(const char *name) noexcept {
    if (std::strcmp(name, "GGML_RISCV_ACCEL_AUTO") == 0)
        return adapter_case == 6 || adapter_case == 18 ? const_cast<char *>("0") : nullptr;
    const char *flags[] = {"GGML_RISCV_QBS_M4_PREFLIGHT", "GGML_RISCV_QBS_M4_PREPARE",
        "GGML_RISCV_QBS_M4_CACHE", "GGML_RISCV_QBS_M4_PACKED", "GGML_RISCV_QBS_M4_PARALLEL_SUMS"};
    for (unsigned i = 0; i < 5; ++i) if (std::strcmp(name, flags[i]) == 0) {
        if (adapter_case == i + 1) return const_cast<char *>("0");
        if (adapter_case == 18) return const_cast<char *>("1");
    }
    return nullptr;
}
extern "C" int NI ggml_graph_n_nodes(ggml_cgraph *) { return graph_count; }
extern "C" ggml_tensor *NI ggml_graph_node(ggml_cgraph *, int i) { return nodes[i]; }
extern "C" bool NI ggml_is_contiguous(const ggml_tensor *t) {
    size_t stride = sizeof(float);
    for (unsigned i = 0; i < 4; ++i) { if (t->nb[i] != stride) return false; stride *= t->ne[i]; }
    return true;
}
extern "C" size_t NI ggml_nbytes(const ggml_tensor *t) {
    return size_t(t->ne[0] * t->ne[1] * t->ne[2] * t->ne[3]) * sizeof(float);
}
bool NI ggml_riscv_qbs_supports_tensor(ggml_type type, int64_t k, int64_t n) {
    return type == GGML_TYPE_Q4_K && (k == 2048 || k == 4096) && n == 64;
}
using planner_signature = bool (*)(ggml_type, int64_t, int64_t, int64_t,
                                  ggml_riscv_qbs_activation_plan *, bool);
static_assert(std::is_same<decltype(&ggml_riscv_qbs_plan_activations), planner_signature>::value,
              "Review the final qbs.h planner signature before sealing this successor");
bool NI ggml_riscv_qbs_plan_activations(ggml_type type, int64_t rows, int64_t outputs, int64_t k,
        ggml_riscv_qbs_activation_plan *plan, bool allow_auto_m8) {
    need(!allow_auto_m8, "M4_eligibility_must_disable_auto_M8");
    need(type == GGML_TYPE_Q4_K && rows == (k == 2048 ? 8 : 4) && outputs == 64 && k == adapter_k,
         "planner_metadata");
    ++planner_calls;
    *plan = {};
    plan->wide_m = adapter_case == 16;
    plan->packed_bytes = size_t(rows / 4) * size_t(k / 256) * sizeof(block_q8_Kx4);
    plan->workspace_bytes = plan->packed_bytes;
    return true;
}

namespace std { const nothrow_t nothrow; }
void *NI operator new[](size_t n, const std::nothrow_t &) noexcept {
    n = (n + 63) & ~size_t(63);
    if (adapter_case == 15 || n > sizeof(heap) - used) return nullptr;
    void *p = heap + used; used += n; return p;
}
void NI operator delete[](void *) noexcept {}
void NI operator delete[](void *, size_t) noexcept {}
extern "C" void NI ggml_quantize_mat_q8_K_4x1_ara_generic(const float *a, void *b, int64_t k) {
    need(b == watched_output && untouched(), "generic_before_any_output_write");
    ++generic_calls;
    frozen_generic(a, b, k);
}
extern "C" void NI ggml_abort(const char *, int, const char *, ...) {
    if (adapter_case == 8) {
        // No vector/libc operation or VSTART clearing is allowed in the abort observation.
        if (vs() != 1 || fc() != 17 || vc() != 5 || candidate_calls != abort_candidates ||
            generic_calls != abort_generics || !watched_cache ||
            watched_cache->bytes.statistics().queries != abort_queries || !actual_untouched()) test_exit(2);
        test_text("M4_ADAPTER_VSTART_PASS"); field(" k=", adapter_k);
        test_text(" candidate_delta=0 generic_delta=0 cache_queries_delta=0 untouched=1 vstart=1\n");
        test_exit(0);
    }
    test_text("M4_ADAPTER_UNEXPECTED_ABORT\n"); test_exit(3);
}
__attribute__((noinline)) static bool prepare(ggml_riscv_q8_K_prepared::state &cache,
        ggml_riscv_m4_reuse::policy policy) {
    return cache.prepare(policy, input, actual + 64, adapter_k, 0, false);
}
static void shape(ggml_tensor &t, int64_t n, int64_t m, void *data) {
    t.type = GGML_TYPE_F32; t.data = data;
    t.ne[0] = n; t.ne[1] = m; t.ne[2] = t.ne[3] = 1; t.nb[0] = 4;
    for (unsigned i = 1; i < 4; ++i) t.nb[i] = t.nb[i - 1] * t.ne[i - 1];
}
static unsigned oracle() {
    std::memset(expected, 0xa5, sizeof(expected));
    watched_output = expected + 64; controls(0, 5);
    const bool vector = ggml_riscv_q8_K_m4_packed::quantize<true>(input, expected + 64, adapter_k);
    need(vector == !(adapter_case >= 11 && adapter_case <= 14), "accepted_packed_oracle_domain");
    return fc() & 31;
}
static void compare(unsigned raised, unsigned flags = 17, unsigned vector_control = 5) {
    need(fc() == (flags | raised) && vc() == vector_control && !vs(), "complete_csr");
    need(!std::memcmp(expected, actual, sizeof(actual)), "complete_payload_and_all_guards");
}
static uint64_t digest(const unsigned char *p, size_t n) {
    uint64_t h = UINT64_C(14695981039346656037);
    for (size_t i = 0; i < n; ++i) h = (h ^ p[i]) * UINT64_C(1099511628211);
    return h;
}

int main() {
    const unsigned k = adapter_k;
    need((k == 2048 || k == 4096) && adapter_case <= 18 && adapter_gate <= 1, "bounded_case_shape");
    const size_t in = size_t(k) * 16, bytes = size_t(k / 256) * sizeof(block_q8_Kx4);
    need(in <= sizeof(input) && bytes + 128 <= sizeof(actual), "dynamic_extents");
    std::memcpy(input, adapter_input, sizeof(input));
    if (adapter_case >= 11 && adapter_case <= 14) {
        const uint32_t invalid[] = {0x00000001u, 0x7f800000u, 0x7fc01234u, 0x7f801234u};
        std::memcpy(input + 4 * k - 1, invalid + adapter_case - 11, 4);
    }
    std::memcpy(saved, input, sizeof(input));
    const unsigned rows = k == 2048 ? 8 : 4;
    shape(x, k, rows, input); shape(w, k, 64, nullptr); w.type = GGML_TYPE_Q4_K; w.extra = &w;
    for (unsigned i = 0; i < 2; ++i) {
        shape(ops[i], 64, rows, results[i]); ops[i].op = GGML_OP_MUL_MAT;
        ops[i].src[0] = &w; ops[i].src[1] = &x;
    }
    graph_count = adapter_case == 10 ? 1 : 2;
    ggml_compute_params params{}; params.nth = adapter_case == 9 ? 2 : 1;
    params.graph_epoch = 1; params.cgraph = &graph; params.node_index = 0;
    ggml_riscv_q8_K_prepared::state cache;
    const auto policy = cache.begin(&params, &ops[0]);
    need(planner_calls > 0 || adapter_case == 9, "actual_supported_calls_new_planner");
    const bool no_lookup = adapter_case == 9 || adapter_case == 10 || adapter_case == 16;
    const bool wanted = adapter_gate && !(adapter_case >= 1 && adapter_case <= 6) && !no_lookup;
    const bool selected = ggml_riscv_q8_K_preflight::enabled(k, cache.single_worker, policy.lookup);
    need(selected == wanted, "reviewed_gate_and_explicit_disables");
#ifdef GGML_USE_RISCV_QBS_M4_PREFLIGHT
    need(ggml_riscv_q8_K_preflight::enabled(1536, true, true) ==
         !(adapter_case >= 1 && adapter_case <= 6), "legacy_1536_gate_preserved");
#endif
    need(ggml_riscv_q8_K_preflight::producer_tag(selected) ==
         (selected ? 4u : ggml_riscv_q8_K_m4_packed::producer_tag()), "tag_before_lookup");
    watched_bytes = bytes;
    const unsigned raised = oracle();
    std::memset(actual, 0xa5, sizeof(actual));
    generic_calls = candidate_calls = 0; watched_output = actual + 64; watched_bytes = bytes;
    if (adapter_case == 7 || no_lookup) {
        const unsigned control = adapter_case == 7 ? 49 : 17;
        controls(control, 5);
        need(!prepare(cache, policy), "rejected_prepare");
        need(fc() == control && vc() == 5 && !vs() && actual_untouched(), "rejected_state_output_guards");
        need(!candidate_calls && !generic_calls && !cache.computations && !cache.bytes.statistics().queries,
             "rejected_before_cache_and_producers");
    } else {
        controls(17, 5); need(prepare(cache, policy), "actual_prepare_completed"); compare(raised);
        need(candidate_calls == unsigned(selected), "actual_candidate_entries");
        if (adapter_case >= 11 && adapter_case <= 14) {
            need(generic_calls == 1 && cache.computations == 1 && cache.generic_computations == 1 &&
                 !cache.bytes.size() && !cache.bytes.statistics().stores, "late_special_single_generic_not_cached");
        } else if (adapter_case == 15) {
            need(!generic_calls && cache.computations == 1 && !cache.generic_computations &&
                 cache.bytes.statistics().allocation_failures == 1 && !cache.bytes.statistics().stores,
                 "allocation_failure_completed_once_no_second_producer");
        } else {
            const auto &stats = cache.bytes.statistics();
            need(!generic_calls && stats.queries == 1 && stats.misses == 1 && !stats.hits && stats.stores == 1,
                 "cold_vector_stored");
            if (adapter_case == 8) {
                std::memset(actual, 0xa5, sizeof(actual)); watched_cache = &cache;
                abort_candidates = candidate_calls; abort_generics = generic_calls;
                abort_queries = cache.bytes.statistics().queries; controls(17, 5);
                asm volatile("csrwi vstart,1" ::: "memory");
                (void)prepare(cache, policy); test_exit(4);
            }
            const unsigned flag_count = adapter_case == 0 ? 32 : 1;
            const unsigned vector_count = adapter_case == 0 ? 8 : 1;
            for (unsigned f = 0; f < flag_count; ++f) for (unsigned v = 0; v < vector_count; ++v) {
                std::memset(actual, 0xa5, sizeof(actual)); controls(f, v);
                need(prepare(cache, policy), "cache_hit_prepare"); compare(raised, f, v);
            }
            need(!generic_calls && candidate_calls == unsigned(selected) && cache.computations == 1 &&
                 cache.bytes.statistics().hits == flag_count * vector_count, "hits_no_producers");
            ggml_riscv_q8_K_cache::key other; other.k = k;
            other.producer_tag = selected ? 3 : 4; unsigned flags = 0;
            need(!cache.bytes.get(other, input, in, actual + 64, bytes, flags), "producer_tag_isolation");
            if (adapter_case == 0) {
                auto cold = [&](ggml_riscv_m4_reuse::policy current) {
                    const auto computations = cache.computations, misses = cache.bytes.statistics().misses;
                    const auto candidates = candidate_calls;
                    const unsigned exceptions = oracle();
                    std::memset(actual, 0xa5, sizeof(actual)); watched_output = actual + 64; controls(17, 5);
                    need(prepare(cache, current), "invalidation_cold"); compare(exceptions);
                    need(cache.computations == computations + 1 && cache.bytes.statistics().misses == misses + 1 &&
                         candidate_calls == candidates + unsigned(selected), "invalidation_producer_accounting");
                };
                auto *raw = reinterpret_cast<unsigned char *>(input);
                raw[in - 1] ^= 0x80; cold(policy); raw[in - 1] ^= 0x80;
                ++params.graph_epoch; auto next = cache.begin(&params, &ops[0]);
                need(next.lookup && !cache.bytes.size() && cache.epoch == params.graph_epoch, "epoch_clears_cache"); cold(next);
                ggml_tensor alternate = x; ops[0].src[1] = ops[1].src[1] = &alternate;
                next = cache.begin(&params, &ops[0]);
                need(next.lookup && !cache.bytes.size() && cache.source == &alternate, "source_identity_clears_cache"); cold(next);
                need(cache.computations == 4 && candidate_calls == 4 * unsigned(selected) && !generic_calls,
                     "all_invalidation_producers");
                test_text("M4_ADAPTER_INVALIDATION_PASS"); field(" k=", k);
                test_text(" quartet_last_byte=1 epoch=1 source=1 computations=4\n");
            }
            if (adapter_case == 17) {
                ggml_riscv_m4_reuse::policy lookup_only{true, false};
                cache.finish(lookup_only);
                need(!cache.bytes.size(), "finish_without_fill_clears");
                std::memset(actual, 0xa5, sizeof(actual)); controls(17, 5);
                need(prepare(cache, lookup_only), "lookup_without_fill_completed"); compare(raised);
                need(cache.computations == 2 && !cache.bytes.size() && cache.bytes.statistics().stores == 1 &&
                     candidate_calls == 2 * unsigned(selected) && !generic_calls, "lookup_without_fill_not_retained");
            }
        }
    }
    const auto &stats = cache.bytes.statistics();
    need(!stats.rejected && !stats.conflicts && !stats.evictions &&
         stats.allocation_failures == unsigned(adapter_case == 15), "cache_error_counters");
    controls(0, 0); need(!std::memcmp(saved, input, sizeof(input)), "all_input_bytes_preserved");
    test_text("M4_ADAPTER_PASS"); field(" k=", k); field(" case=", adapter_case);
    field(" selected=", selected); field(" checks=", checks); field(" candidate_entries=", candidate_calls);
    field(" generic_entries=", generic_calls); field(" computations=", cache.computations);
    field(" queries=", stats.queries); field(" hits=", stats.hits); field(" misses=", stats.misses);
    field(" stores=", stats.stores); field(" allocation_failures=", stats.allocation_failures);
    field(" planner_calls=", planner_calls); field(" bytes=", bytes);
    field(" payload_hash=", digest(expected + 64, bytes)); test_text(" guards=1 input_preserved=1 errors=0\n");
    return 0;
}
extern "C" int NI strcmp(const char *a, const char *b) {
    while (*a && *a == *b) { ++a; ++b; }
    return int(static_cast<unsigned char>(*a)) - int(static_cast<unsigned char>(*b));
}
