#include "q8_K-m4-packed.h"

extern "C" bool m4_packed_produce(const float *x, void *y, int64_t k) {
    return ggml_riscv_q8_K_m4_packed::quantize(x, y, k);
}
