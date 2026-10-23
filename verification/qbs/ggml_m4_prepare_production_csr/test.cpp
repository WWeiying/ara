#include "arch-fallback.h"
#include "repack.h"

#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <vector>

// Declaration only: the definition must come from the production repack TU.
template <int64_t INTER_SIZE, ggml_type PARAM_TYPE>
void ggml_quantize_mat_t(const float * GGML_RESTRICT x, void * GGML_RESTRICT y,
                         int64_t nrow, int64_t k);
template <>
void ggml_quantize_mat_t<1, GGML_TYPE_Q8_0>(const float * GGML_RESTRICT x,
                                           void * GGML_RESTRICT y, int64_t nrow, int64_t k);

static unsigned read_fcsr() {
    unsigned value;
    asm volatile("frcsr %0" : "=r"(value) : : "memory");
    return value;
}
static void write_fcsr(unsigned value) {
    asm volatile("fscsr %0" : : "r"(value) : "memory");
}
static unsigned read_vcsr() {
    unsigned value;
    asm volatile("csrr %0, vcsr" : "=r"(value) : : "memory");
    return value;
}
static void write_vcsr(unsigned value) {
    asm volatile("csrw vcsr, %0" : : "r"(value) : "memory");
}

[[noreturn]] static void fail(const char * name, const char * reason, unsigned frm, unsigned flags) {
    std::fprintf(stderr, "M4_TU_CSR_FAIL case=%s reason=%s frm=%u flags=%u\n", name, reason, frm, flags);
    std::exit(1);
}

static unsigned policy(const char * name) {
    const char * value = std::getenv(name);
    if (!value || (std::strcmp(value, "0") && std::strcmp(value, "1")))
        fail("policy", name, 0, 0);
    return unsigned(value[0] - '0');
}

extern "C" __attribute__((noinline))
void m4_tu_production_call(const float * x, void * y, int64_t k) {
    ggml_quantize_mat_t<1, GGML_TYPE_Q8_0>(x, y, 4, k);
}
extern "C" __attribute__((noinline))
void m4_tu_oracle_call(const float * x, void * y, int64_t k) {
    ggml_quantize_mat_q8_0_4x1_generic(x, y, k);
}

static uint64_t hash_bytes(uint64_t hash, const void * data, size_t size) {
    const auto * bytes = static_cast<const unsigned char *>(data);
    for (size_t i = 0; i < size; ++i) hash = (hash ^ bytes[i]) * UINT64_C(1099511628211);
    return hash;
}

static unsigned mode, trace;
static size_t checks, datasets;
static uint64_t suite_digest = UINT64_C(14695981039346656037);

static void check(const char * name, const std::vector<float> & input, bool /* eligible */,
                  bool check_ties = false) {
    const int64_t k = int64_t(input.size() / 4);
    const size_t blocks = size_t(k / QK8_0);
    const auto unchanged = input;
    std::vector<block_q8_0x4> expected(blocks + 2), actual(blocks + 2);
    std::array<unsigned char, sizeof(block_q8_0x4)> guard;
    guard.fill(0xa5);
    const size_t dataset = datasets++;
    for (unsigned frm = 0; frm <= 4; ++frm) {
        for (unsigned seed : {0U, 8U, 31U}) {
            const unsigned initial = (frm << 5) | seed;
            const unsigned vcsr = (frm + seed) & 7;
            std::memset(expected.data(), 0xa5, expected.size() * sizeof(expected[0]));
            std::memset(actual.data(), 0xa5, actual.size() * sizeof(actual[0]));
            std::memset(expected.data() + 1, 0x3c, blocks * sizeof(expected[0]));
            std::memset(actual.data() + 1, 0xc3, blocks * sizeof(actual[0]));
            std::printf("M4_TU_CASE_BEGIN seq=%zu dataset=%zu k=%lld frm=%u flags=%u vcsr=%u\n",
                        checks, dataset, (long long) k, frm, seed, vcsr);
            write_fcsr(initial);
            write_vcsr(vcsr);
            m4_tu_oracle_call(input.data(), expected.data() + 1, k);
            const unsigned expected_fcsr = read_fcsr(), expected_vcsr = read_vcsr();
            write_fcsr(initial);
            write_vcsr(vcsr);
            m4_tu_production_call(input.data(), actual.data() + 1, k);
            const unsigned actual_fcsr = read_fcsr(), actual_vcsr = read_vcsr();
            write_fcsr(0);
            if (actual_fcsr != expected_fcsr || (actual_fcsr >> 5) != frm ||
                (actual_fcsr & seed) != seed) fail(name, "fcsr_mismatch", frm, seed);
            if (actual_vcsr != vcsr || expected_vcsr != vcsr) fail(name, "vcsr_mismatch", frm, seed);
            if (std::memcmp(actual.data(), expected.data(), actual.size() * sizeof(actual[0])))
                fail(name, "byte_mismatch", frm, seed);
            for (size_t index : {size_t(0), blocks + 1}) {
                if (std::memcmp(&actual[index], guard.data(), guard.size()) ||
                    std::memcmp(&expected[index], guard.data(), guard.size()))
                    fail(name, "output_overrun", frm, seed);
            }
            if (check_ties) {
                for (int row = 0; row < 4; ++row)
                    if (actual[1].qs[4 + row] != 1 || actual[1].qs[8 + row] != -1)
                        fail(name, "ties_not_away", frm, seed);
                if (expected_fcsr != initial) fail(name, "roundf_flags_contract", frm, seed);
            }
            uint64_t hash = hash_bytes(UINT64_C(14695981039346656037), actual.data() + 1,
                                       blocks * sizeof(actual[0]));
            hash = hash_bytes(hash, &actual_fcsr, sizeof(actual_fcsr));
            hash = hash_bytes(hash, &actual_vcsr, sizeof(actual_vcsr));
            suite_digest = hash_bytes(suite_digest, &hash, sizeof(hash));
            std::printf("M4_TU_CASE_PASS seq=%zu digest=%016llx fcsr=%u vcsr=%u\n",
                        checks, static_cast<unsigned long long>(hash), actual_fcsr, actual_vcsr);
            ++checks;
        }
    }
    if (!input.empty() && std::memcmp(input.data(), unchanged.data(), input.size() * sizeof(float)))
        fail(name, "input_modified", 0, 0);
}

static std::vector<float> pattern(int blocks, float scale) {
    const int k = blocks * QK8_0;
    std::vector<float> x(4 * k);
    for (int row = 0; row < 4; ++row) {
        for (int b = 0; b < blocks; ++b) {
            for (int j = 0; j < QK8_0; ++j) {
                const int value = ((j * 17 + row * 13 + b * 7) % 253) - 126;
                x[row * k + b * QK8_0 + j] = scale * static_cast<float>(value);
            }
            x[row * k + b * QK8_0] = 127.0f * scale;
        }
    }
    return x;
}

static float from_bits(uint32_t bits) {
    float value;
    std::memcpy(&value, &bits, sizeof(value));
    return value;
}

int main(int argc, char ** argv) {
    if (argc != 2) fail("capture", "expected_capture_path", 0, 0);
    mode = policy("GGML_RISCV_QBS_M4_PREPARE");
    trace = policy("GGML_RISCV_QBS_TRACE_M4_PREPARE");
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    const unsigned saved_fcsr = read_fcsr(), saved_vcsr = read_vcsr();
    write_fcsr(0);
    std::vector<float> x(128, 0.0f);
    check("zero", x, true);
    for (float & value : x) value = -0.0f;
    check("negative_zero", x, true);
    for (int j = 0; j < 128; ++j) x[j] = j % 2 ? -0.0f : 0.0f;
    check("mixed_zero", x, true);

    x = pattern(1, 1.0f);
    for (int row = 0; row < 4; ++row) {
        x[row * 32 + 1] = 0.5f;
        x[row * 32 + 2] = -0.5f;
        x[row * 32 + 3] = 126.5f;
        x[row * 32 + 4] = -126.5f;
        x[row * 32 + 5] = -127.0f;
    }
    check("exact_ties_away", x, true, true);
    for (int row = 0; row < 4; ++row) {
        x[row * 32 + 1] = std::nextafter(0.5f, 0.0f);
        x[row * 32 + 2] = std::nextafter(-0.5f, 0.0f);
        x[row * 32 + 3] = std::nextafter(0.5f, 1.0f);
        x[row * 32 + 4] = std::nextafter(-0.5f, -1.0f);
        if (row & 1) { x[row * 32] = -127.0f; x[row * 32 + 5] = 127.0f; }
    }
    check("near_ties_mixed_extrema", x, true);

    for (int blocks : {2, 17, 28, 32, 33}) check("multi_block", pattern(blocks, 0.125f), true);
    // Around half subnormal/normal, ties-to-even, and overflow boundaries.
    for (float scale : {0x1p-25f, 0x1p-24f, 0x1p-14f, 1.0f + 0x1p-11f,
                        1.0f + 3 * 0x1p-11f, 65504.0f, 65520.0f}) {
        for (float direction : {0.0f, scale, std::numeric_limits<float>::infinity()}) {
            check("half_scale_boundary", pattern(2, std::nextafter(scale, direction)), true);
        }
    }
    // Deterministic broad finite data, not restricted to integer products.
    uint32_t state = 0x9672a5e1U;
    for (int trial = 0; trial < 32; ++trial) {
        x.resize(4 * 32 * (1 + trial % 3));
        for (float & value : x) {
            state = state * 1664525U + 1013904223U;
            const unsigned exponent = 30 + ((state >> 23) % 210);
            value = from_bits((state & 0x807fffffU) | (exponent << 23));
        }
        check("finite_bits", x, true);
    }
    check("small_guard_boundary", pattern(1, 0x1p-117f), false);
    check("safe_small", pattern(1, 0x1p-110f), true);
    check("tiny_normal_reciprocal_overflow", std::vector<float>(128, 0x1p-126f), false);
    check("tiny_subnormal", std::vector<float>(128, from_bits(1)), false);
    // Exceptional generic behavior is not a portable numerical guarantee:
    // these compare delegation against this exact compiled production object.
    for (uint32_t bits : {0x00000001U, 0x80000001U, 0x7f800000U, 0xff800000U,
                          0x7fc00001U, 0x7f800001U}) {
        x = pattern(2, 1.0f);
        x.back() = from_bits(bits);
        check("late_exception_fallback", x, false);
    }
    check("maximum_finite", std::vector<float>(128, std::numeric_limits<float>::max()), true);
    // k=0 must neither write output nor change the caller's environment.
    check("empty", {}, false);
    std::vector<float> capture(4 * 896);
    FILE * stream = std::fopen(argv[1], "rb");
    if (!stream || std::fread(capture.data(), sizeof(float), capture.size(), stream) != capture.size()
            || std::fgetc(stream) != EOF) fail("capture", "invalid_real_capture", 0, 0);
    std::fclose(stream);
    check("real_qwen25_projection_m4_k896", capture, true);
    write_fcsr(saved_fcsr);
    write_vcsr(saved_vcsr);
    if (datasets != 76 || checks != 1140) fail("coverage", "missing_cases", 0, 0);
    std::printf("M4_TU_CSR_PASS mode=%u trace=%u datasets=%zu checks=%zu digest=%016llx bytes=exact fcsr=exact vcsr=exact\n",
                mode, trace, datasets, checks, static_cast<unsigned long long>(suite_digest));
    return 0;
}
