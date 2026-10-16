#include "simd-mappings.h"

static uint16_t input[65536];
static float output[65536];

__attribute__((noinline, optimize("no-tree-vectorize")))
static uint32_t reference(uint16_t h) {
    uint32_t sign = (uint32_t)(h & 0x8000) << 16;
    uint32_t exp = (h >> 10) & 31;
    uint32_t frac = h & 1023;
    if (exp == 31) return sign | 0x7f800000 | (frac << 13);
    if (exp) return sign | ((exp + 112) << 23) | (frac << 13);
    if (!frac) return sign;
    int e = -14;
    while (!(frac & 1024)) { frac <<= 1; --e; }
    return sign | ((uint32_t)(e + 127) << 23) | ((frac & 1023) << 13);
}

__attribute__((noinline))
static void convert(void) {
    for (unsigned i = 0; i < 65536; ++i)
        output[i] = GGML_CPU_FP16_TO_FP32(input[i]);
}

void _start(void) {
    int failed = 0;
    for (unsigned i = 0; i < 65536; ++i) input[i] = i;
    convert();
    for (unsigned i = 0; i < 65536; ++i) {
        uint32_t got;
        memcpy(&got, &output[i], 4);
        uint32_t want = reference(i);
        if ((i & 0x7c00) == 0x7c00 && (i & 1023)) {
            if ((got & 0x7f800000) != 0x7f800000 || !(got & 0x7fffff)) failed = 1;
        } else if (got != want) failed = 1;
    }
    register long a0 asm("a0") = failed;
    register long a7 asm("a7") = 93;
    asm volatile("ecall" : : "r"(a0), "r"(a7) : "memory");
    __builtin_unreachable();
}
