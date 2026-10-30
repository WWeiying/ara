#include "ggml-cpu/vec.h"

/* Call the production inline helpers, without copying their implementations. */
void quant_kv_ggml_mad_f32(int n, float *y, const float *x, float scale) {
  ggml_vec_mad_f32(n, y, x, scale);
}

void quant_kv_ggml_scale_f32(int n, float *y, float scale) {
  ggml_vec_scale_f32(n, y, scale);
}
