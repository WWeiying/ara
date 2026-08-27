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
  ggml_half d[Q4K_BENCH_ROWS];
  uint8_t hmask[(QK_K / 8) * Q4K_BENCH_ROWS];
  uint8_t qs[(QK_K / 4) * Q4K_BENCH_ROWS];
  uint8_t scales[12 * Q4K_BENCH_ROWS];
} block_q3_Kx32_ara;

typedef struct {
  ggml_half d[Q4K_BENCH_ROWS];
  ggml_half dmin[Q4K_BENCH_ROWS];
  uint8_t scales[K_SCALE_SIZE * Q4K_BENCH_ROWS];
  uint8_t qh[(QK_K / 8) * Q4K_BENCH_ROWS];
  uint8_t qs[(QK_K / 2) * Q4K_BENCH_ROWS];
} block_q5_Kx32_ara;

typedef struct {
  ggml_half d[Q4K_BENCH_ROWS];
  int8_t scales[(QK_K / 16) * Q4K_BENCH_ROWS];
  uint8_t ql[(QK_K / 2) * Q4K_BENCH_ROWS];
  uint8_t qh[(QK_K / 4) * Q4K_BENCH_ROWS];
} block_q6_Kx32_ara;

typedef struct {
  ggml_half d[Q4K_BENCH_ROWS];
  int8_t qs[QK8_0 * Q4K_BENCH_ROWS];
} block_q8_0x32_ara;

typedef struct {
  float d[Q4K_BENCH_INPUTS];
  int8_t qs[QK_K * Q4K_BENCH_INPUTS];
  int16_t bsums[QK_K / 4];
} block_q8_Kx4;

_Static_assert(sizeof(block_q4_Kx32_ara) == sizeof(block_q4_K) * 32,
               "invalid Q4_Kx32 layout");
_Static_assert(sizeof(block_q3_Kx32_ara) == sizeof(block_q3_K) * 32,
               "invalid Q3_Kx32 layout");
_Static_assert(sizeof(block_q5_Kx32_ara) == sizeof(block_q5_K) * 32,
               "invalid Q5_Kx32 layout");
_Static_assert(sizeof(block_q6_Kx32_ara) == sizeof(block_q6_K) * 32,
               "invalid Q6_Kx32 layout");
_Static_assert(sizeof(block_q8_0x32_ara) == sizeof(block_q8_0) * 32,
               "invalid Q8_0x32 layout");
_Static_assert(sizeof(block_q8_Kx4) == sizeof(block_q8_K) * 4,
               "invalid Q8_Kx4 layout");

float q4k_dot_original(const block_q4_K *weight, const block_q8_K *activation,
                       int n);
float q4k_dot_vl1024(const block_q4_K *weight, const block_q8_K *activation,
                     int n);
void q4k_gemv_32(const block_q4_Kx32_ara *weight, const block_q8_K *activation,
                 float *output, int n);
void q4k_gemm_32x4(const block_q4_Kx32_ara *weight,
                   const block_q8_Kx4 *activation, float *output, int n);
void q3k_gemv_32(const block_q3_Kx32_ara *weight,
                 const block_q8_K *activation, float *output, int n);
void q5k_gemv_32(const block_q5_Kx32_ara *weight,
                 const block_q8_K *activation, float *output, int n);
void q6k_gemv_32(const block_q6_Kx32_ara *weight, const block_q8_K *activation,
                 float *output, int n);
void q6k_gemm_32x4(const block_q6_Kx32_ara *weight,
                   const block_q8_K *activation, int activation_stride,
                   float *output, int output_stride, int n);
void q8_0_gemv_32(const block_q8_0x32_ara *weight,
                  const block_q8_0 *activation, float *output, int n);

#endif
