#ifndef LLAMA_Q4KM_MICRO_KERNELS_H_
#define LLAMA_Q4KM_MICRO_KERNELS_H_

#include <stddef.h>
#include <stdint.h>

#define QK_K 256
#define QK8_0 32
#define K_SCALE_SIZE 12

typedef uint16_t ggml_half;

typedef struct {
  ggml_half d;
  int8_t qs[QK8_0];
} block_q8_0;

typedef struct {
  ggml_half d;
  uint8_t qs[QK8_0 / 2];
} block_q4_0;

typedef struct {
  ggml_half d;
  uint8_t qh[QK8_0 / 8];
  uint8_t qs[QK8_0 / 2];
} block_q5_0;

typedef struct {
  ggml_half d;
  uint8_t qs[QK8_0 / 2];
} block_iq4_nl;

typedef struct {
  uint8_t scales[QK_K / 16];
  uint8_t qs[QK_K / 4];
  ggml_half d;
  ggml_half dmin;
} block_q2_K;

typedef struct {
  uint8_t hmask[QK_K / 8];
  uint8_t qs[QK_K / 4];
  uint8_t scales[12];
  ggml_half d;
} block_q3_K;

typedef struct {
  union {
    struct {
      ggml_half d;
      ggml_half dmin;
    };
    uint32_t dm;
  };
  uint8_t scales[K_SCALE_SIZE];
  uint8_t qs[QK_K / 2];
} block_q4_K;

typedef struct {
  union {
    struct {
      ggml_half d;
      ggml_half dmin;
    };
    uint32_t dm;
  };
  uint8_t scales[K_SCALE_SIZE];
  uint8_t qh[QK_K / 8];
  uint8_t qs[QK_K / 2];
} block_q5_K;

typedef struct {
  uint8_t ql[QK_K / 2];
  uint8_t qh[QK_K / 4];
  int8_t scales[QK_K / 16];
  ggml_half d;
} block_q6_K;

typedef struct {
  float d;
  int8_t qs[QK_K];
  int16_t bsums[QK_K / 16];
} block_q8_K;

_Static_assert(sizeof(block_q4_K) == 144, "invalid Q4_K layout");
_Static_assert(sizeof(block_q3_K) == 110, "invalid Q3_K layout");
_Static_assert(sizeof(block_q5_K) == 176, "invalid Q5_K layout");
_Static_assert(sizeof(block_q6_K) == 210, "invalid Q6_K layout");
_Static_assert(sizeof(block_q8_0) == 34, "invalid Q8_0 layout");
_Static_assert(sizeof(block_q4_0) == 18, "invalid Q4_0 layout");
_Static_assert(sizeof(block_q5_0) == 22, "invalid Q5_0 layout");
_Static_assert(sizeof(block_iq4_nl) == 18, "invalid IQ4_NL layout");
_Static_assert(sizeof(block_q2_K) == 84, "invalid Q2_K layout");
_Static_assert(sizeof(block_q8_K) == 292, "invalid Q8_K layout");

void q4km_quantize_row_q8_0(const float *x, block_q8_0 *y, int64_t k);
void q4km_quantize_row_q8_K(const float *x, block_q8_K *y, int64_t k);
float q4km_vec_dot_q3_K_q8_K(const block_q3_K *x, const block_q8_K *y, int n);
float q4km_vec_dot_q4_K_q8_K(const block_q4_K *x, const block_q8_K *y, int n);
float q4km_vec_dot_q5_K_q8_K(const block_q5_K *x, const block_q8_K *y, int n);
float q4km_vec_dot_q6_K_q8_K(const block_q6_K *x, const block_q8_K *y, int n);
float q4km_vec_dot_q8_0_q8_0(const block_q8_0 *x, const block_q8_0 *y, int n);
float q4km_vec_dot_q4_0_q8_0(const block_q4_0 *x, const block_q8_0 *y, int n);
float q4km_vec_dot_q5_0_q8_0(const block_q5_0 *x, const block_q8_0 *y, int n);
float q4km_vec_dot_iq4_nl_q8_0(const block_iq4_nl *x,
                               const block_q8_0 *y, int n);
float q4km_vec_dot_q2_K_q8_K(const block_q2_K *x,
                             const block_q8_K *y, int n);

#endif
