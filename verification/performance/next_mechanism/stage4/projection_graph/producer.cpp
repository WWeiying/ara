#include "q8_K-m4-packed.h"
#include "m4_preflight.h"

extern "C" __attribute__((noinline)) bool stage4_baseline_produce(
    const float *input, void *output, int64_t k) {
    return ggml_riscv_q8_K_m4_packed::quantize<true>(input,output,k);
}

extern "C" __attribute__((noinline)) bool stage4_candidate_produce(
    const float *input, void *output, int64_t k) {
    return qbs_experimental_m4_preflight::quantize(input,output,k);
}
