#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <math.h>
#include "ggml-quants.h"

void ggml_abort(const char *file, int line, const char *fmt, ...) {
  va_list ap; va_start(ap,fmt); fprintf(stderr,"%s:%d ",file,line);
  vfprintf(stderr,fmt,ap); va_end(ap); abort();
}
static void require(int ok) { if (!ok) { fputs("requantization I/O/nonfinite error\n",stderr); exit(1); } }
static void save(const char *dir, const char *name, const void *p, size_t n) {
  char path[4096]; require(snprintf(path,sizeof(path),"%s/%s",dir,name)<(int)sizeof(path));
  FILE *f=fopen(path,"wb"); require(f && fwrite(p,1,n,f)==n && !fclose(f));
}
int main(int argc, char **argv) {
  require(argc==3);
  enum { N=64,K=2048 };
  block_q4_K *source=malloc(N*(K/256)*sizeof(*source));
  float *weights=malloc(N*K*sizeof(*weights));
  unsigned char *quant=malloc(N*(K/32)*34);
  require(source && weights && quant);
  FILE *f=fopen(argv[1],"rb");
  require(f && fread(source,sizeof(*source),N*(K/256),f)==N*(K/256));
  require(!fclose(f));
  dequantize_row_q4_K(source,weights,N*K);
  for (unsigned i=0; i<N*K; ++i) require(isfinite(weights[i]));
  save(argv[2],"dequantized_q4_K_f32.bin",weights,N*K*4);
#define QUANT(fmt,be,wb) do { \
  _Static_assert(sizeof(block_##fmt)==wb,"upstream weight ABI changed"); \
  quantize_row_##fmt##_ref(weights,(block_##fmt *)quant,N*K); \
  save(argv[2],"weight_" #fmt ".bin",quant,N*(K/be)*wb); \
} while(0)
  QUANT(q2_K,256,84); QUANT(q3_K,256,110); QUANT(q4_K,256,144);
  QUANT(q5_K,256,176); QUANT(q6_K,256,210); QUANT(q4_0,32,18);
  QUANT(q5_0,32,22); QUANT(q8_0,32,34); QUANT(iq4_nl,32,18);
  puts("Q4_K actual source -> upstream dequantize -> F32 derivative -> nine upstream ref quantizers; NOT original F16; NOT nine native model captures");
  free(quant); free(weights); free(source); return 0;
}
