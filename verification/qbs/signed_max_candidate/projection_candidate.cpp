// Distinct namespace prevents COMDAT coalescing with the accepted quantizer.
#define ggml_riscv_q8_K_m4 signed_max_quantizer
#include "q8_K-m4.h"
#undef ggml_riscv_q8_K_m4

extern "C" __attribute__((noinline)) bool candidate_prepare(
        const float *input, void *output, int64_t k) {
    return signed_max_quantizer::quantize(input, output, k);
}
