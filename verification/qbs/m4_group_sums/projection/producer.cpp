#include "q8_K-m4-packed.h"
#include "../quantizer_candidate.h"
extern "C" bool sums_current_produce(const float *x,void *y,int64_t k) {
  return ggml_riscv_q8_K_m4_packed::quantize(x,y,k);
}
extern "C" bool sums_parallel_produce(const float *x,void *y,int64_t k) {
  return qbs_m4_parallel_sums::quantize(x,y,k);
}
