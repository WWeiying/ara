#include "q8_K-prepared-cache.h"
#include "m4_preflight.h"

extern "C" const float extension_input[];
extern "C" void frozen_generic(const float *, void *, int64_t);
extern "C" void test_text(const char *);
extern "C" void test_number(uint64_t);
extern "C" void test_exit(unsigned) __attribute__((noreturn));

static constexpr unsigned MaxK = 4096, MaxBytes = MaxK / 256 * sizeof(block_q8_Kx4);
alignas(64) static unsigned char golden[MaxBytes], output[MaxBytes + 128], heap[128 * 1024];
static bool allocated;
static unsigned generic_calls;

static unsigned fcsr() { unsigned x; asm volatile("frcsr %0" : "=r"(x) :: "memory"); return x; }
static unsigned vcsr() { unsigned x; asm volatile("csrr %0,vcsr" : "=r"(x) :: "memory"); return x; }
static unsigned vstart() { unsigned x; asm volatile("csrr %0,vstart" : "=r"(x) :: "memory"); return x; }
static uint64_t cycle() { uint64_t x; asm volatile("fence rw,rw;rdcycle %0" : "=r"(x) :: "memory"); return x; }
static uint64_t retired() { uint64_t x; asm volatile("rdinstret %0" : "=r"(x) :: "memory"); return x; }
static void state() { asm volatile("csrwi fcsr,17;csrwi vcsr,5;csrwi vstart,0" ::: "memory"); }
static void need(bool ok, const char *reason) {
    if (!ok) { test_text("EXT_PREFLIGHT_FAIL reason="); test_text(reason); test_text("\n"); test_exit(1); }
}
static uint8_t *allocate(size_t n) {
    if (allocated || n > sizeof(heap)) return nullptr;
    allocated = true;
    return heap;
}
void operator delete[](void *) noexcept {}
void operator delete[](void *, size_t) noexcept {}
extern "C" char *getenv(const char *) noexcept { return const_cast<char *>("1"); }
extern "C" void ggml_quantize_mat_q8_K_4x1_ara_generic(const float *x, void *y, int64_t k) {
    ++generic_calls;
    frozen_generic(x, y, k);
}
extern "C" __attribute__((noinline)) bool extension_baseline(const float *x, void *y, int64_t k) {
    return ggml_riscv_q8_K_m4_packed::quantize<true>(x, y, k);
}
extern "C" __attribute__((noinline)) bool extension_candidate(const float *x, void *y, int64_t k) {
    return qbs_experimental_m4_preflight::quantize(x, y, k);
}
static void field(const char *name, uint64_t value) { test_text(name); test_number(value); }
static uint64_t payload_hash(const unsigned char *p, size_t n) {
    uint64_t h = UINT64_C(14695981039346656037);
    for (size_t i = 0; i < n; ++i) h = (h ^ p[i]) * UINT64_C(1099511628211);
    return h;
}

int main() {
    unsigned width;
    asm volatile("csrr %0,vlenb" : "=r"(width) :: "memory");
    need(width == 128, "vlen");
    for (unsigned shape = 0; shape < 2; ++shape) {
        const unsigned k = shape ? 4096 : 2048;
        const size_t in = size_t(k) * 16, bytes = k / 256 * sizeof(block_q8_Kx4);
        state();
        need(extension_baseline(extension_input, golden, k), "baseline_vector");
        const unsigned expected_fcsr = fcsr();
        state();
        need(extension_candidate(extension_input, output + 64, k), "candidate_vector");
        need(!std::memcmp(golden, output + 64, bytes) && fcsr() == expected_fcsr && vcsr() == 5,
             "warmup_bytes_flags");
        for (unsigned trial = 0; trial < 4; ++trial) {
            allocated = false;
            ggml_riscv_q8_K_cache::value_cache<> cache(allocate);
            const bool candidate = trial == 1 || trial == 2;
            ggml_riscv_q8_K_cache::key key;
            key.k = k; key.producer_tag = candidate ? 4 : 3;
            std::memset(output, 0xa5, sizeof(output));
            state();
            const uint64_t inst = retired(), begin = cycle();
            unsigned producers = 0;
            for (unsigned call = 0; call < 3; ++call) {
                unsigned raised = 0;
                const unsigned before = fcsr();
                if (!cache.get(key, extension_input, in, output + 64, bytes, raised)) {
                    asm volatile("fsflags zero" ::: "memory");
                    const bool vector = candidate ? extension_candidate(extension_input, output + 64, k)
                                                  : extension_baseline(extension_input, output + 64, k);
                    asm volatile("frflags %0" : "=r"(raised) :: "memory");
                    const unsigned flags = (before & 31u) | raised;
                    asm volatile("fsflags %0" :: "r"(flags) : "memory");
                    need(vector && cache.put(key, extension_input, in, output + 64, bytes, raised), "cold_store");
                    ++producers;
                }
                const unsigned flags = (before & 31u) | raised;
                asm volatile("fsflags %0" :: "r"(flags) : "memory");
            }
            const uint64_t end = cycle(), instructions = retired() - inst;
            const auto stats = cache.statistics();
            need(fcsr() == expected_fcsr && vcsr() == 5 && !vstart(), "call_csr");
            need(!std::memcmp(golden, output + 64, bytes), "complete_bytes");
            need(stats.queries == 3 && stats.hits == 2 && stats.misses == 1 && stats.stores == 1 &&
                 producers == 1 && !stats.rejected && !stats.conflicts && !stats.allocation_failures && !stats.evictions,
                 "cache_accounting");
            for (unsigned i = 0; i < 64; ++i)
                need(output[i] == 0xa5 && output[64 + bytes + i] == 0xa5, "guards");
            test_text("EXT_PREFLIGHT_TRIAL"); field(" k=", k); field(" trial=", trial);
            field(" candidate=", candidate); field(" cycles=", end - begin); field(" instructions=", instructions);
            field(" bytes=", bytes); field(" fcsr=", fcsr()); field(" vcsr=", vcsr());
            field(" queries=", stats.queries); field(" hits=", stats.hits); field(" producers=", producers);
            field(" misses=", stats.misses); field(" stores=", stats.stores);
            field(" rejected=", stats.rejected); field(" conflicts=", stats.conflicts);
            field(" allocation_failures=", stats.allocation_failures); field(" evictions=", stats.evictions);
            field(" comparison_bytes_requested=", stats.comparison_bytes_requested);
            field(" copied_payload_bytes=", stats.copied_payload_bytes);
            field(" vstart=", vstart()); field(" guard_bytes=", 128); field(" payload_equal=", 1);
            field(" payload_hash=", payload_hash(output + 64, bytes));
            test_text(" errors=0\n");
        }
    }
    need(generic_calls == 0, "unexpected_generic");
    test_text("EXT_PREFLIGHT_DONE shapes=2 trials=8 calls=24 errors=0\n");
    return 0;
}
