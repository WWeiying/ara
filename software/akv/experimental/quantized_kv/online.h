#ifndef AKV_QUANTIZED_KV_ONLINE_H
#define AKV_QUANTIZED_KV_ONLINE_H

#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

/* Software schedule for quantized KV, not new AKV quantized-payload hardware.
 * Admission must establish a finite, zero-mask visible prefix before entry.
 * Both schedules preserve each head's original token-order F32 operations.
 * Callers must not retry fallback after any callback has executed. */
enum {
  AKV_QUANT_MAX_HEADS = 8,
  AKV_QUANT_MAX_DIM = 256,
  AKV_QUANT_TILE = 32,
  AKV_QUANT_MAX_TOKENS = 65536,
  AKV_QUANT_OK = 0,
  AKV_QUANT_BAD_ARGUMENT = 1,
  AKV_QUANT_QK_FAILED = 2,
  AKV_QUANT_VALUE_FAILED = 3,
};

typedef int (*akv_quant_qk_fn)(void *, unsigned first_head, unsigned heads,
    unsigned first_token, unsigned tokens, float *scores, size_t row_stride);
typedef int (*akv_quant_value_fn)(void *, unsigned token, float *value, unsigned dim);
typedef void (*akv_quant_scale_fn)(int dim, float *output, float scale);
typedef void (*akv_quant_mad_fn)(int dim, float *output, const float *value, float weight);

typedef struct {
  unsigned heads, dim, tokens;
  float score_scale;
  void *context;
  akv_quant_qk_fn qk;
  akv_quant_value_fn value;
  akv_quant_scale_fn scale;
  akv_quant_mad_fn mad;
} akv_quant_online_plan_t;

typedef struct __attribute__((aligned(64))) {
  float score[AKV_QUANT_MAX_HEADS][AKV_QUANT_TILE];
  float value[AKV_QUANT_MAX_DIM];
  float maximum[AKV_QUANT_MAX_HEADS], sum[AKV_QUANT_MAX_HEADS];
} akv_quant_online_workspace_t;

static inline int akv_quant_online_valid(const akv_quant_online_plan_t *p,
    const float *output, size_t stride, const akv_quant_online_workspace_t *w) {
  if (!p || !output || !w || !p->qk || !p->value || !p->scale || !p->mad ||
      !p->heads || p->heads > AKV_QUANT_MAX_HEADS ||
      !p->dim || p->dim > AKV_QUANT_MAX_DIM || p->dim % 32 ||
      !p->tokens || p->tokens > AKV_QUANT_MAX_TOKENS || stride < p->dim)
    return 0;
  if (p->heads > 1 && stride >
      (SIZE_MAX / sizeof(float) - p->dim) / (p->heads - 1))
    return 0;
  uint32_t bits;
  memcpy(&bits, &p->score_scale, sizeof(bits));
  return bits && !(bits & UINT32_C(0x80000000)) &&
         (bits & UINT32_C(0x7f800000)) != UINT32_C(0x7f800000);
}

static inline void akv_quant_online_init(const akv_quant_online_plan_t *p,
    float *output, size_t stride, akv_quant_online_workspace_t *w) {
  for (unsigned head = 0; head < p->heads; ++head) {
    memset(output + head * stride, 0, p->dim * sizeof(float));
    w->maximum[head] = -INFINITY;
    w->sum[head] = 0.0f;
  }
}

static inline void akv_quant_online_step(const akv_quant_online_plan_t *p,
    unsigned head, float score, const float *value, float *output,
    akv_quant_online_workspace_t *w) {
  /* Mirrors GGML's quantized-V F32 branch, including scale then zero mask. */
  float s = score * p->score_scale;
  s += 0.0f;
  const float old = w->maximum[head];
  float ms = 1.0f, vs = 1.0f;
  if (s > w->maximum[head]) {
    w->maximum[head] = s;
    ms = expf(old - s);
    p->scale((int)p->dim, output, ms);
  } else {
    vs = expf(s - w->maximum[head]);
  }
  p->mad((int)p->dim, output, value, vs);
  w->sum[head] = w->sum[head] * ms + vs;
}

static inline void akv_quant_online_finish(const akv_quant_online_plan_t *p,
    float *output, size_t stride, akv_quant_online_workspace_t *w) {
  for (unsigned head = 0; head < p->heads; ++head) {
    const float inverse = w->sum[head] == 0.0f ? 0.0f : 1.0f / w->sum[head];
    p->scale((int)p->dim, output + head * stride, inverse);
  }
}

/* Reference schedule: each head loads/decodes its own V for every token. */
static inline int akv_quant_online_head_major(const akv_quant_online_plan_t *p,
    float *output, size_t stride, akv_quant_online_workspace_t *w) {
  if (!akv_quant_online_valid(p, output, stride, w)) return AKV_QUANT_BAD_ARGUMENT;
  akv_quant_online_init(p, output, stride, w);
  for (unsigned head = 0; head < p->heads; ++head) {
    for (unsigned token = 0; token < p->tokens; ++token) {
      if (p->qk(p->context, head, 1, token, 1, &w->score[0][0], AKV_QUANT_TILE))
        return AKV_QUANT_QK_FAILED;
      if (p->value(p->context, token, w->value, p->dim)) return AKV_QUANT_VALUE_FAILED;
      akv_quant_online_step(p, head, w->score[0][0], w->value, output + head * stride, w);
    }
  }
  akv_quant_online_finish(p, output, stride, w);
  return AKV_QUANT_OK;
}

/* Shared schedule: QBS groups4/2/1 heads, each V row decoded once per tile. */
static inline int akv_quant_online_shared(const akv_quant_online_plan_t *p,
    float *output, size_t stride, akv_quant_online_workspace_t *w) {
  if (!akv_quant_online_valid(p, output, stride, w)) return AKV_QUANT_BAD_ARGUMENT;
  akv_quant_online_init(p, output, stride, w);
  for (unsigned first = 0; first < p->tokens; first += AKV_QUANT_TILE) {
    const unsigned remaining = p->tokens - first;
    const unsigned tokens = remaining < AKV_QUANT_TILE ? remaining : AKV_QUANT_TILE;
    for (unsigned head = 0; head < p->heads;) {
      const unsigned left = p->heads - head;
      const unsigned rows = left >= 4 ? 4 : left >= 2 ? 2 : 1;
      if (p->qk(p->context, head, rows, first, tokens, &w->score[head][0], AKV_QUANT_TILE))
        return AKV_QUANT_QK_FAILED;
      head += rows;
    }
    for (unsigned token = 0; token < tokens; ++token) {
      if (p->value(p->context, first + token, w->value, p->dim)) return AKV_QUANT_VALUE_FAILED;
      for (unsigned head = 0; head < p->heads; ++head)
        akv_quant_online_step(p, head, w->score[head][token], w->value, output + head * stride, w);
    }
  }
  akv_quant_online_finish(p, output, stride, w);
  return AKV_QUANT_OK;
}

#endif
