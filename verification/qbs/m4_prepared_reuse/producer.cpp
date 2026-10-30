#include "q8_K-m4.h"

extern "C" bool m4_produce(const float *x,void *y,int64_t k) {
    return ggml_riscv_q8_K_m4::quantize<16>(x,y,k);
}
