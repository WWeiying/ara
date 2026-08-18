#ifndef LLAMA_Q4K_REPACK_BENCH_KERNELS_H_
#define LLAMA_Q4K_REPACK_BENCH_KERNELS_H_

#include "../llama_q4km_micro/micro_kernels.h"

#define Q4K_BENCH_K 1536
#define Q4K_BENCH_ROWS 32
#define Q4K_BENCH_INPUTS 4
#define Q4K_BENCH_BLOCKS (Q4K_BENCH_K / QK_K)

typedef struct {
  ggml_half d[Q4K_BENCH_ROWS];
  ggml_half dmin[Q4K_BENCH_ROWS];
  uint8_t scales[K_SCALE_SIZE * Q4K_BENCH_ROWS];
  uint8_t qs[(QK_K / 2) * Q4K_BENCH_ROWS];
} block_q4_Kx32_ara;

typedef struct {
  float d[Q4K_BENCH_INPUTS];
  int8_t qs[QK_K * Q4K_BENCH_INPUTS];
  int16_t bsums[QK_K / 4];
} block_q8_Kx4;

_Static_assert(sizeof(block_q4_Kx32_ara) == sizeof(block_q4_K) * 32,
               "invalid Q4_Kx32 layout");
_Static_assert(sizeof(block_q8_Kx4) == sizeof(block_q8_K) * 4,
               "invalid Q8_Kx4 layout");

float q4k_dot_original(const block_q4_K *weight,
                       const block_q8_K *activation, int n);
float q4k_dot_vl1024(const block_q4_K *weight,
                     const block_q8_K *activation, int n);
void q4k_gemv_32(const block_q4_Kx32_ara *weight,
                 const block_q8_K *activation, float *output, int n);
void q4k_gemm_32x4(const block_q4_Kx32_ara *weight,
                   const block_q8_Kx4 *activation, float *output, int n);

#endif
