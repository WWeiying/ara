#include "m4_preflight.h"
#include <initializer_list>

namespace candidate = qbs_experimental_m4_preflight;
extern "C" void frozen_generic(const float *, void *, int64_t);
extern "C" const float real_input[];
extern "C" void test_text(const char *);
extern "C" void test_number(uint64_t);
extern "C" void test_exit(unsigned) __attribute__((noreturn));
constexpr unsigned max_k = 6400, bytes = max_k/256*4*sizeof(block_q8_K);
alignas(64) static float input[4*max_k], saved[4*max_k];
alignas(64) static unsigned char baseline[bytes+128], output[bytes+128];
static unsigned checks, metadata_checks, generic_entries, vector_cases, generic_cases;
static unsigned large_cases, real_cases, current_pattern, current_k;
static unsigned watched_fc, watched_vc;
static void *watched_output;

static unsigned fc() { unsigned x; asm volatile("frcsr %0":"=r"(x)::"memory"); return x; }
static unsigned vc() { unsigned x; asm volatile("csrr %0,vcsr":"=r"(x)::"memory"); return x; }
static unsigned vs() { unsigned x; asm volatile("csrr %0,vstart":"=r"(x)::"memory"); return x; }
static void state(unsigned f, unsigned v) {
    asm volatile("csrw fcsr,%0;csrw vcsr,%1;csrwi vstart,0"::"r"(f),"r"(v):"memory");
}
static void need(bool ok, const char *why) {
    if (ok) return;
    test_text("FAIL check="); test_number(checks);
    test_text(" metadata="); test_number(metadata_checks);
    test_text(" k="); test_number(current_k);
    test_text(" pattern="); test_number(current_pattern);
    test_text(" reason="); test_text(why); test_text("\n"); test_exit(1);
}
extern "C" void ggml_quantize_mat_q8_K_4x1_ara_generic(const float *x, void *y, int64_t k) {
    need(y == watched_output, "fallback_destination");
    need(fc() == watched_fc && vc() == watched_vc && vs() == 0, "fallback_entry_csr");
    const auto *p = static_cast<const unsigned char *>(y);
    for (size_t i = 0; i < size_t(k/256)*sizeof(block_q8_Kx4); ++i)
        need(p[i] == 0xa5, "fallback_entry_output_touched");
    ++generic_entries;
    frozen_generic(x, y, k);
}
extern "C" __attribute__((noinline)) bool accepted_produce(const float *x, void *y, int64_t k) {
    return ggml_riscv_q8_K_m4_packed::quantize<true>(x, y, k);
}
extern "C" __attribute__((noinline)) bool candidate_produce(const float *x, void *y, int64_t k) {
    return candidate::quantize(x, y, k);
}
static uint32_t bits(float x) { uint32_t u; std::memcpy(&u, &x, 4); return u; }
static void put(float *x, uint32_t u) { std::memcpy(x, &u, 4); }
static uint32_t scalar_max(const float *x, bool &valid) {
    uint32_t best = 0, signed_best = 0, minimum = UINT32_MAX;
    for (unsigned i = 0; i < 256; ++i) {
        const uint32_t word = bits(x[i]), absolute = word & 0x7fffffff;
        if (absolute > best) { best = absolute; signed_best = word; }
        if (absolute - 1 < minimum) minimum = absolute - 1;
    }
    valid &= minimum >= 0x007fffff && (!best || (best >= 0x08800000 && best <= 0x77000000));
    return signed_best;
}
template <size_t AVL>
__attribute__((noinline)) static bool preflight_probe(const float *x, int64_t k, candidate::maxima &m) {
    return candidate::preflight<AVL>(x, k, m);
}
template <size_t AVL>
__attribute__((noinline)) static void metadata(unsigned k) {
    struct { uint64_t before; candidate::maxima data; uint64_t after; } m;
    std::memset(&m, 0xa5, sizeof(m));
    state(17, 5);
    bool valid = true;
    candidate::maxima expected{};
    for (unsigned b = 0; b < k/256; ++b)
        for (unsigned row = 0; row < 4; ++row)
            expected.signed_bits[b][row] = scalar_max(input + row*k + b*256, valid);
    const unsigned initial = fc();
    const bool got = preflight_probe<AVL>(input, k, m.data);
    need(fc() == initial && vc() == 5 && vs() == 0, "integer_preflight_csr");
    need(got == valid, "domain_decision");
    need(m.before == UINT64_C(0xa5a5a5a5a5a5a5a5) && m.after == m.before, "metadata_guard");
    if (valid) need(std::memcmp(&m.data, &expected, k/256*16) == 0, "first_global_signed_max");
    ++metadata_checks;
}
static void compare(unsigned k, unsigned f = 17, unsigned v = 5) {
    current_k = k;
    std::memcpy(saved, input, sizeof(input));
    std::memset(baseline, 0xa5, sizeof(baseline));
    std::memset(output, 0xa5, sizeof(output));
    watched_fc = f; watched_vc = v; watched_output = baseline + 64;
    state(f, v); const bool a = accepted_produce(input, baseline + 64, k);
    const unsigned af = fc(), av = vc(), as = vs();
    watched_output = output + 64;
    state(f, v); const bool b = candidate_produce(input, output + 64, k);
    const unsigned bf = fc(), bv = vc(), bs = vs();
    need(a == b, "producer_selection");
    need(af == bf && av == bv && as == bs && bs == 0, "producer_csr");
    need(std::memcmp(baseline, output, sizeof(output)) == 0, "complete_bytes");
    const size_t size = k/256*sizeof(block_q8_Kx4);
    for (size_t i = 0; i < 64; ++i)
        need(output[i] == 0xa5 && output[64+size+i] == 0xa5, "output_guard");
    need(std::memcmp(input, saved, sizeof(input)) == 0, "input_modified");
    ++checks; vector_cases += a; generic_cases += !a; large_cases += k > candidate::max_k;
}
static void fill(unsigned k, unsigned pattern) {
    current_pattern = pattern;
    for (unsigned i = 0; i < 4*k; ++i) input[i] = float(int((i*17 + i/256*7)%127)-63)/512.0f;
    for (unsigned row = 0; row < 4; ++row) for (unsigned b = 0; b < k/256; ++b) {
        float *x = input + row*k + b*256;
        if (pattern == 1) for (unsigned i = 0; i < 256; ++i) put(x+i, (i&1)<<31);
        if (pattern == 2) { x[31] = 2.0f; x[32] = -2.0f; x[255] = -2.0f; }
        if (pattern == 3) { x[3] = -2.0f; x[35] = 2.0f; x[224] = 2.0f; }
        if (pattern == 4 || pattern == 5)
            for (unsigned i = 0; i < 256; ++i) put(x+i, ((i&1)<<31) | (pattern == 4 ? 0x08800000u : 0x77000000u));
    }
    if (k && pattern >= 6) {
        const uint32_t invalid[] = {0x00000001, 0x007fffff, 0x7f800000, 0x7fc01234, 0x7f801234};
        put(input + 4*k-1, invalid[pattern-6]);
    }
}
int main() {
    unsigned vlenb;
    asm volatile("csrr %0,vlenb":"=r"(vlenb)::"memory");
    test_text("STAGE4_M4_VLEN bits="); test_number(vlenb*8); test_text("\n");
    for (unsigned k : {256u, 512u, 1536u, 6144u, 6400u}) {
        for (unsigned pattern = 0; pattern < 11; ++pattern) {
            fill(k, pattern); compare(k);
            if (k <= candidate::max_k) {
                metadata<1>(k); metadata<7>(k); metadata<13>(k); metadata<32>(k);
            }
        }
    }
    fill(256, 0);
    for (unsigned frm = 1; frm <= 4; ++frm)
        for (unsigned sticky : {0u, 17u}) compare(256, frm*32+sticky);
    for (uint32_t limit : {0x087fffffu, 0x77000001u}) {
        for (unsigned i = 0; i < 4*256; ++i) put(input+i, limit);
        compare(256); metadata<13>(256);
    }
    compare(0, 0); compare(0, 17);
    current_pattern = 100;
    std::memcpy(input, real_input, 4*1536*sizeof(float));
    for (unsigned sticky = 0; sticky < 32; ++sticky)
        for (unsigned v = 0; v < 8; ++v) { compare(1536, sticky, v); ++real_cases; }
    need(checks == 323 && metadata_checks == 178 && real_cases == 256 && large_cases == 11,
         "exercise_counts");
    need(vector_cases > 0 && generic_cases > 0 && generic_entries == 2*generic_cases, "fallback_exercise");
    test_text("STAGE4_M4_PREFLIGHT_PASS checks="); test_number(checks);
    test_text(" metadata="); test_number(metadata_checks);
    test_text(" real="); test_number(real_cases);
    test_text(" large="); test_number(large_cases);
    test_text(" vector="); test_number(vector_cases);
    test_text(" generic="); test_number(generic_cases);
    test_text(" fallback_entries="); test_number(generic_entries);
    test_text(" bytes_flags_guards=exact performance=not_measured\n");
    return 0;
}
