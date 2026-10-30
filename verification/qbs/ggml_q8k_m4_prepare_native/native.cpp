#include "../ggml_q8k_m4_prepare_candidate.h"

#include <array>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

static unsigned csr_read() { unsigned x; asm volatile("frcsr %0" : "=r"(x) : : "memory"); return x; }
static void csr_write(unsigned x) { asm volatile("fscsr %0" : : "r"(x) : "memory"); }
static unsigned vcsr_read() { unsigned x; asm volatile("csrr %0,vcsr" : "=r"(x) : : "memory"); return x; }
static void vcsr_write(unsigned x) { asm volatile("csrw vcsr,%0" : : "r"(x) : "memory"); }
static float from_bits(uint32_t x) { float f; std::memcpy(&f, &x, 4); return f; }

[[noreturn]] static void fail(const char * name, const char * why, unsigned frm = 0,
                            unsigned seed = 0, size_t cap = 0) {
    std::fprintf(stderr, "Q8K_M4_FAIL case=%s reason=%s frm=%u seed=%u cap=%zu\n", name, why, frm, seed, cap);
    std::exit(1);
}

__attribute__((noinline)) static void oracle(const float * x, void * y, int64_t k) {
    ggml_quantize_mat_q8_K_4x1_ara_generic(x, y, k);
}

__attribute__((noinline)) static bool candidate(const float * x, void * y, int64_t k, size_t cap) {
    switch (cap) {
        case 1: return qbs_q8k_m4_prepare_candidate::quantize<1>(x, y, k);
        case 7: return qbs_q8k_m4_prepare_candidate::quantize<7>(x, y, k);
        case 16: return qbs_q8k_m4_prepare_candidate::quantize<16>(x, y, k);
        default: fail("dispatch", "invalid_cap");
    }
}

static size_t cases = 0, checks = 0, vectors = 0, fallbacks = 0;
static void check(const std::string & name, const std::vector<float> & values, bool eligible,
                  bool fma_witness = false, bool underflow_witness = false) {
    static_assert(sizeof(block_q8_Kx4) == 1168, "unexpected M4 layout");
    if (values.size() % (4 * QK_K)) fail(name.c_str(), "invalid_shape");
    const int64_t k = values.size() / 4;
    const size_t blocks = k / QK_K;
    std::vector<float> input(values.size() + 32, from_bits(1));
    std::memcpy(input.data() + 16, values.data(), values.size() * sizeof(float));
    const auto unchanged = input;
    std::vector<block_q8_Kx4> expected(blocks + 2), actual(blocks + 2);
    std::array<unsigned char, sizeof(block_q8_Kx4)> guard;
    guard.fill(0xa5);
    const unsigned seeds[] = {0, 1, 2, 4, 8, 16, 31, 0};
    size_t local_vector = 0, local_checks = 0;
    uint64_t hash = UINT64_C(14695981039346656037);
    for (unsigned frm = 0; frm < 5; ++frm) {
        for (unsigned env = 0; env < 8; ++env) {
            for (size_t cap : {size_t(1), size_t(7), size_t(16)}) {
                const unsigned initial = (frm << 5) | seeds[env];
                std::memset(expected.data(), 0xa5, expected.size() * sizeof(expected[0]));
                std::memset(actual.data(), 0xa5, actual.size() * sizeof(actual[0]));
                std::memset(expected.data() + 1, 0x3c, blocks * sizeof(expected[0]));
                std::memset(actual.data() + 1, 0xc3, blocks * sizeof(actual[0]));
                csr_write(initial); vcsr_write(env);
                oracle(input.data() + 16, expected.data() + 1, k);
                const unsigned ef = csr_read(), ev = vcsr_read();
                csr_write(initial); vcsr_write(env);
                const bool used = candidate(input.data() + 16, actual.data() + 1, k, cap);
                const unsigned af = csr_read(), av = vcsr_read();
                csr_write(0);
                if (used != (eligible && frm == 0 && k != 0)) fail(name.c_str(), "path", frm, env, cap);
                if (af != ef || (af >> 5) != frm || (af & seeds[env]) != seeds[env]) {
                    std::fprintf(stderr, "fcsr expected=%u actual=%u\n", ef, af);
                    fail(name.c_str(), "fcsr", frm, env, cap);
                }
                if (ev != env || av != env) fail(name.c_str(), "vcsr", frm, env, cap);
                if (std::memcmp(expected.data(), actual.data(), actual.size() * sizeof(actual[0]))) {
                    fail(name.c_str(), "bytes", frm, env, cap);
                }
                for (size_t index : {size_t(0), blocks + 1}) {
                    if (std::memcmp(&actual[index], guard.data(), guard.size()) ||
                        std::memcmp(&expected[index], guard.data(), guard.size())) fail(name.c_str(), "guard", frm, env, cap);
                }
                if (std::memcmp(input.data(), unchanged.data(), input.size() * sizeof(float))) {
                    fail(name.c_str(), "input_modified", frm, env, cap);
                }
                for (size_t b = 1; b <= blocks; ++b) {
                    for (int group = 0; group < 16; ++group) {
                        for (int row = 0; row < 4; ++row) {
                            int sum = 0;
                            for (int j = 0; j < 16; ++j) sum += actual[b].qs[4 * (group * 16 + j) + row];
                            if (sum != actual[b].bsums[4 * group + row]) fail(name.c_str(), "bsums", frm, env, cap);
                        }
                    }
                }
                if (frm == 0 && fma_witness) {
                    for (int row = 0; row < 4; ++row) {
                        if (expected[1].qs[4 + row] != 11 || actual[1].qs[4 + row] != 11)
                            fail(name.c_str(), "not_pinned_fma_contract", frm, env, cap);
                    }
                }
                if (frm == 0 && underflow_witness && ((af | ef) & 2) != (initial & 2)) {
                    fail(name.c_str(), "split_multiply_underflow", frm, env, cap);
                }
                const auto * bytes = reinterpret_cast<const unsigned char *>(actual.data() + 1);
                for (size_t j = 0; j < blocks * sizeof(actual[0]); ++j) {
                    hash = (hash ^ bytes[j]) * UINT64_C(1099511628211);
                }
                ++local_checks;
                local_vector += used;
            }
        }
    }
    std::printf("Q8K_M4_CASE_PASS id=%zu name=%s k=%lld eligible=%u checks=%zu vector=%zu fallback=%zu digest=%016llx\n",
                cases++, name.c_str(), (long long) k, unsigned(eligible), local_checks, local_vector,
                local_checks - local_vector, (unsigned long long) hash);
    checks += local_checks; vectors += local_vector; fallbacks += local_checks - local_vector;
}

static std::vector<float> pattern(int blocks) {
    const int k = blocks * 256;
    std::vector<float> x(4 * k);
    for (int row = 0; row < 4; ++row) {
        for (int b = 0; b < blocks; ++b) {
            for (int j = 0; j < 256; ++j) x[row*k+b*256+j] = float((row*13+b*19+j*17)%253-126) * 0.125f;
            x[row*k+b*256] = -127.0f * 0.125f;
        }
    }
    return x;
}

int main(int argc, char ** argv) {
    if (argc != 2) fail("args", "capture_list_required");
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    const unsigned saved_fcsr = csr_read(), saved_vcsr = vcsr_read();
    size_t vlenb;
    asm volatile("csrr %0,vlenb" : "=r"(vlenb));
    std::printf("Q8K_M4_BEGIN vlen=%zu cases=50\n", 8*vlenb);
    csr_write(0);
    std::vector<float> x(1024, 0.0f);
    check("zero", x, true);
    for (float & value : x) value = -0.0f;
    check("negative_zero", x, true);
    for (size_t j = 0; j < x.size(); ++j) x[j] = j%2 ? -0.0f : 0.0f;
    check("mixed_zero", x, true);
    for (int variant = 0; variant < 3; ++variant) {
        x.assign(1024, 0.0f);
        for (int row = 0; row < 4; ++row) {
            const float first = variant == 1 ? -127.0f : 127.0f;
            x[row*256 + (variant == 2 ? 15 : 0)] = row%2 ? -first : first;
            x[row*256 + (variant == 2 ? 16 : 255)] = row%2 ? first : -first;
            x[row*256+31] = 10.5f;
        }
        check(variant == 0 ? "first_max_pos" : variant == 1 ? "first_max_neg" : "first_max_boundary", x, true);
    }
    x.assign(1024, 0.0f);
    for (int row = 0; row < 4; ++row) {
        x[row*256] = -127;
        for (int j = 1; j < 256; ++j) x[row*256+j] = ((j%2) ? 1 : -1) * ((j%63) + 0.5f);
    }
    check("ties_even", x, true);
    x.assign(1024, 0.0f);
    for (int row = 0; row < 4; ++row) {
        x[row*256] = from_bits(0x3f800001U);
        x[row*256+1] = from_bits(0xbda952a7U); // Negative x, not a negated bit pattern.
    }
    check("fma_rounding", x, true, true);
    x.assign(1024, from_bits(0x00800000U));
    for (int row = 0; row < 4; ++row) x[row*256] = from_bits(0x77000000U);
    check("fused_underflow", x, true, false, true);
    x = pattern(2);
    for (int row = 0; row < 4; ++row) {
        for (int b = 0; b < 2; ++b) {
            for (int j : {7, 14, 15, 16, 31, 32, 127, 128, 239, 240, 255}) x[row*512+b*256+j] = float(j%29-14);
        }
    }
    check("bsums_boundary", x, true);
    for (int row = 0; row < 4; ++row) for (int j = 0; j < 256; ++j) x[row*256+j] = ((j/16+row)%2) ? -127.0f : 127.0f;
    x.resize(1024);
    check("bsums_extrema", x, true);
    for (int blocks : {2,4,5,6,17,28,32,33,35,65}) check("blocks_" + std::to_string(blocks), pattern(blocks), true);
    const uint32_t bounds[] = {0x087fffffU,0x08800000U,0x08800001U,0x76ffffffU,0x77000000U,0x77000001U};
    const char * names[] = {"low_below","low_equal","low_above","high_below","high_equal","high_above"};
    for (size_t i = 0; i < 6; ++i) check(names[i], std::vector<float>(1024, from_bits(bounds[i])), i != 0 && i != 5);
    check("tiny_normal", std::vector<float>(1024, from_bits(0x00800000U)), false);
    check("max_finite", std::vector<float>(1024, from_bits(0x7f7fffffU)), false);
    const uint32_t exceptional[] = {1U,0x80000001U,0x7f800000U,0xff800000U,0x7fc00001U,0x7f800001U};
    for (size_t i = 0; i < 6; ++i) {
        x = pattern(2); x.back() = from_bits(exceptional[i]);
        check("late_exception_" + std::to_string(i), x, false);
    }
    check("empty", {}, false);
    uint32_t state = 0x426a127bU;
    for (int trial = 0; trial < 8; ++trial) {
        x.resize(4*256*(1+trial%3));
        for (float & value : x) {
            state = 1664525U*state + 1013904223U;
            value = from_bits((state & 0x807fffffU) | ((30 + (state>>23)%200) << 23));
        }
        check("finite_" + std::to_string(trial), x, true);
    }
    FILE * list = std::fopen(argv[1], "r");
    if (!list) fail("capture", "missing_list");
    for (unsigned id = 0; id < 6; ++id) {
        unsigned index = 99, k = 0; char name[80], path[160];
        if (std::fscanf(list, "%u %79s %u %159s", &index, name, &k, path) != 4 || index != id ||
            k != (id < 4 ? 1536U : 8960U)) fail("capture", "bad_list");
        x.resize(4 * k);
        FILE * stream = std::fopen(path, "rb");
        if (!stream || std::fread(x.data(), 4, x.size(), stream) != x.size() || std::fgetc(stream) != EOF)
            fail("capture", "bad_size");
        std::fclose(stream);
        check(name, x, true);
    }
    char extra[2];
    if (std::fscanf(list, "%1s", extra) != EOF) fail("capture", "extra_list_record");
    std::fclose(list);
    if (cases != 50 || checks != 6000 || vectors != 936 || fallbacks != 5064) fail("coverage", "counts");
    csr_write(saved_fcsr); vcsr_write(saved_vcsr);
    std::printf("Q8K_M4_PASS cases=%zu checks=%zu vector=%zu fallback=%zu bytes=exact bsums=exact fcsr=exact vcsr=exact guards=exact\n",
                cases, checks, vectors, fallbacks);
    return 0;
}
