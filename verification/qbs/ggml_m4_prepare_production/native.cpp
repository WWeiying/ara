#include "arch/riscv/q8_0-m4.h"

#include <array>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <vector>

static unsigned read_fcsr() {
    unsigned result;
    asm volatile("frcsr %0" : "=r"(result) : : "memory");
    return result;
}

static void write_fcsr(unsigned value) {
    asm volatile("fscsr %0" : : "r"(value) : "memory");
}

static unsigned read_vcsr() {
    unsigned result;
    asm volatile("csrr %0, vcsr" : "=r"(result) : : "memory");
    return result;
}

static void write_vcsr(unsigned value) {
    asm volatile("csrw vcsr, %0" : : "r"(value) : "memory");
}

[[noreturn]] static void fail(const char * name, const char * reason,
                            unsigned frm, unsigned seed, size_t cap) {
    std::fprintf(stderr, "M4_PRODUCTION_BYTES_FAIL case=%s reason=%s frm=%u flags=%u cap=%zu\n",
                 name, reason, frm, seed, cap);
    std::exit(1);
}

// Keep CSR writes outside the arithmetic functions, even under optimization.
__attribute__((noinline)) static void oracle(const float * x, void * y, int64_t k) {
    ggml_quantize_mat_q8_0_4x1_generic(x, y, k);
}

__attribute__((noinline)) static bool candidate(const float * x, void * y, int64_t k, size_t cap) {
    switch (cap) {
        case 1: return ggml_riscv_q8_0_m4::quantize<1>(x, y, k);
        case 7: return ggml_riscv_q8_0_m4::quantize<7>(x, y, k);
        default: return ggml_riscv_q8_0_m4::quantize<32>(x, y, k);
    }
}

static size_t checks = 0, vector_checks = 0, fallback_checks = 0;

static void check(const char * name, const std::vector<float> & input, bool eligible,
                  bool check_ties = false) {
    const int64_t k = static_cast<int64_t>(input.size() / 4);
    const size_t blocks = static_cast<size_t>(k / QK8_0);
    const auto unchanged = input;
    std::vector<block_q8_0x4> expected(blocks + 2), actual(blocks + 2);
    std::array<unsigned char, sizeof(block_q8_0x4)> guard;
    guard.fill(0xa5);
    for (unsigned frm = 0; frm <= 4; ++frm) {
        for (unsigned seed : {0U, 8U, 31U}) {
            for (size_t cap : {size_t(1), size_t(7), size_t(32)}) {
                std::memset(expected.data(), 0xa5, expected.size() * sizeof(expected[0]));
                std::memset(actual.data(), 0xa5, actual.size() * sizeof(actual[0]));
                // Different initial payloads also catch unwritten output bytes.
                std::memset(expected.data() + 1, 0x3c, blocks * sizeof(expected[0]));
                std::memset(actual.data() + 1, 0xc3, blocks * sizeof(actual[0]));
                const unsigned initial = (frm << 5) | seed;
                const unsigned vcsr = (frm + seed) & 7;
                write_fcsr(initial);
                write_vcsr(vcsr);
                oracle(input.data(), expected.data() + 1, k);
                const unsigned expected_fcsr = read_fcsr();
                const unsigned expected_vcsr = read_vcsr();
                write_fcsr(initial);
                write_vcsr(vcsr);
                const bool used = candidate(input.data(), actual.data() + 1, k, cap);
                const unsigned actual_fcsr = read_fcsr();
                const unsigned actual_vcsr = read_vcsr();
                write_fcsr(0);
                if (used != (eligible && frm == 0 && k != 0)) fail(name, "wrong_path", frm, seed, cap);
                if ((actual_fcsr >> 5) != frm || (expected_fcsr >> 5) != frm) {
                    fail(name, "frm_not_restored", frm, seed, cap);
                }
                if (actual_fcsr != expected_fcsr) {
                    std::fprintf(stderr, "fcsr expected=%u actual=%u\n", expected_fcsr, actual_fcsr);
                    fail(name, "fflags_mismatch", frm, seed, cap);
                }
                if ((actual_fcsr & seed) != seed) fail(name, "sticky_flags_lost", frm, seed, cap);
                if (expected_vcsr != vcsr || actual_vcsr != vcsr) fail(name, "vcsr_changed", frm, seed, cap);
                if (std::memcmp(actual.data(), expected.data(), actual.size() * sizeof(actual[0]))) {
                    fail(name, "byte_mismatch", frm, seed, cap);
                }
                for (size_t index : {size_t(0), blocks + 1}) {
                    if (std::memcmp(&actual[index], guard.data(), guard.size()) ||
                        std::memcmp(&expected[index], guard.data(), guard.size())) {
                        fail(name, "output_overrun", frm, seed, cap);
                    }
                }
                if (check_ties) {
                    for (int row = 0; row < 4; ++row) {
                        if (actual[1].qs[4 + row] != 1 || actual[1].qs[8 + row] != -1) {
                            fail(name, "ties_not_away", frm, seed, cap);
                        }
                    }
                    if (expected_fcsr != initial) fail(name, "roundf_flags_contract", frm, seed, cap);
                }
                ++checks;
                used ? ++vector_checks : ++fallback_checks;
            }
        }
    }
    if (!input.empty() && std::memcmp(input.data(), unchanged.data(), input.size() * sizeof(float))) {
        fail(name, "input_modified", 0, 0, 0);
    }
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
    if (argc != 2) fail("capture", "expected_capture_path", 0, 0, 0);
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
            || std::fgetc(stream) != EOF) fail("capture", "invalid_real_capture", 0, 0, 0);
    std::fclose(stream);
    check("real_qwen25_projection_m4_k896", capture, true);
    write_fcsr(saved_fcsr);
    write_vcsr(saved_vcsr);
    if (checks != 3420 || vector_checks != 594 || fallback_checks != 2826) fail("coverage", "missing_path", 0, 0, 0);
    std::printf("M4_PRODUCTION_BYTES_PASS checks=%zu vector=%zu fallback=%zu bytes=exact fcsr=exact vcsr=exact\n",
                checks, vector_checks, fallback_checks);
    return 0;
}
