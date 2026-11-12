#include "ggml.h"
#include "akv/akv_features.h"
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <type_traits>
#include <sys/reboot.h>
#include <unistd.h>

static_assert(std::is_same<decltype(std::pow(float{}, uint32_t{})), double>::value, "Live integer exponent uses double pow");
static_assert(std::is_same<decltype(::powf(float{}, uint32_t{})), float>::value, "GGML exponent uses float powf");
static_assert(std::is_same<decltype(std::pow(float{}, float{})), float>::value, "Live base uses float powf");

#include "decode_features.inc"

static unsigned csr() {
    unsigned value;
    asm volatile("frcsr %0" : "=r"(value) :: "memory");
    return value;
}

static uint32_t bits(float value) {
    uint32_t result;
    std::memcpy(&result, &value, sizeof(result));
    return result;
}

static void reset(unsigned flags = 0) {
    asm volatile("csrw fcsr,%0;li t0,5;csrw vcsr,t0;csrwi vstart,0" :: "r"(flags) : "t0", "memory");
}

__attribute__((noinline)) static float live_power(float base, uint32_t exponent) {
    return std::pow(base, exponent);
}

__attribute__((noinline)) static float ggml_power(float base, uint32_t exponent) {
    return ::powf(base, exponent);
}

__attribute__((noinline)) static float live_base(float bias, uint32_t heads) {
    return std::pow(2.0f, -bias / heads);
}

__attribute__((noinline)) static float ggml_base(float bias, uint32_t heads) {
    return ::powf(2.0f, -bias / heads);
}

int main() {
    setvbuf(stdout, nullptr, _IONBF, 0);
    volatile float bias_input = 8.0f;
    volatile uint32_t heads_input = 32;
    const float bias = bias_input;
    const uint32_t heads = heads_input;
    reset();
    const float m0 = live_base(bias, heads);
    const unsigned base_csr = csr();
    reset();
    const float reference_m0 = ggml_base(bias, heads);
    const unsigned reference_base_csr = csr();
    std::printf("ALIBI_TYPES float_uint32=double powf=float float_float=float\n");
    std::printf("ALIBI_BASE heads=%u max_bias_bits=%08x live=%08x ggml=%08x live_fcsr=%u ggml_fcsr=%u\n",
                heads, bits(bias), bits(m0), bits(reference_m0), base_csr, reference_base_csr);
    unsigned bit_differences = 0, flag_differences = 0;
    uint32_t live_bits[32], ggml_bits[32];
    for (uint32_t h = 0; h < heads; ++h) {
        reset();
        const float actual = live_power(m0, h + 1);
        const unsigned actual_csr = csr();
        reset();
        const float expected = ggml_power(reference_m0, h + 1);
        const unsigned expected_csr = csr();
        live_bits[h] = bits(actual);
        ggml_bits[h] = bits(expected);
        bit_differences += live_bits[h] != ggml_bits[h];
        flag_differences += actual_csr != expected_csr;
        std::printf("ALIBI_COEFF head=%u exponent=%u live=%08x ggml=%08x live_fcsr=%u ggml_fcsr=%u\n",
                    h, h + 1, live_bits[h], ggml_bits[h], actual_csr, expected_csr);
    }
    ggml_tensor q{}, dst{};
    q.ne[2] = heads;
    dst.src[0] = &q;
    std::memcpy(reinterpret_cast<float *>(dst.op_params) + 1, &bias, sizeof(bias));
    unsigned full_mismatches = 0;
    for (uint32_t first = 0; first < heads; first += 8) {
        akv_attention_features_t features{};
        reset();
        const bool valid = decode_features(&dst, first, 8, 1, &features);
        const unsigned group_csr = csr();
        for (unsigned h = 0; h < 8; ++h)
            full_mismatches += bits(features.mask_scale[h]) != live_bits[first + h];
        std::printf("ALIBI_LIVE_GROUP first=%u rows=8 valid=%u fcsr=%u\n", first, unsigned(valid), group_csr);
        if (!valid) ++full_mismatches;
    }
    reset(31);
    volatile float sticky = live_power(m0, 17);
    const unsigned sticky_live = csr();
    reset(31);
    sticky = ggml_power(reference_m0, 17);
    const unsigned sticky_ggml = csr();
    (void)sticky;
    unsigned vcsr, vstart;
    asm volatile("csrr %0,vcsr;csrr %1,vstart" : "=r"(vcsr), "=r"(vstart) :: "memory");
    std::printf("ALIBI_STICKY live_fcsr=%u ggml_fcsr=%u vcsr=%u vstart=%u\n", sticky_live, sticky_ggml, vcsr, vstart);
    const int status = full_mismatches || bits(m0) != bits(reference_m0) || sticky_live != 31 || sticky_ggml != 31 || vcsr != 5 || vstart != 0;
    std::printf("ALIBI_TARGET_DONE comparisons=32 bit_differences=%u fcsr_differences=%u full_mismatches=%u status=%d\n",
                bit_differences, flag_differences, full_mismatches, status);
    std::fflush(nullptr);
    if (getpid() == 1) {
        sync(); reboot(RB_POWER_OFF); for (;;) pause();
    }
    return status;
}
