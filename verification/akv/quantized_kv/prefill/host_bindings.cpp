#include "ggml-cpu.h"
#include "ggml-quants.h"
#include "ggml-cpu/quants.h"
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
#include "ggml-cpu/vec.h"
#pragma GCC diagnostic pop

extern "C" void prefill_host_init(void) { ggml_cpu_init(); }
extern "C" void prefill_host_quantize(const float *x,void *out,int64_t n) {
    quantize_row_q8_0(x,out,n);
}
extern "C" void prefill_host_decode(const void *x,float *out,int64_t n) {
    dequantize_row_q8_0(static_cast<const block_q8_0 *>(x),out,n);
}
extern "C" void prefill_host_scale(int n,float *out,float s) { ggml_vec_scale_f32(n,out,s); }
extern "C" void prefill_host_mad(int n,float *out,const float *x,float s) { ggml_vec_mad_f32(n,out,x,s); }
