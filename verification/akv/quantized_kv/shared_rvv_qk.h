#ifndef AKV_TEST_SHARED_RVV_QK_H
#define AKV_TEST_SHARED_RVV_QK_H

#include "software/akv/experimental/quantized_kv/online.h"

/* Matches production ggml_vec_dot_q{4,8}_0_q8_0. Bind the actual RVV
 * implementation in the native caller; this helper neither decodes nor gathers.
 * Query rows must already be quantized once using the caller's production path.
 * All Query heads here belong to selectedkv, not an entire multi-KV graph. */
typedef void (*shared_rvv_dot_fn)(int, float *, size_t,
    const void *, size_t, const void *, size_t, int);

typedef struct {
  const void *key, *query;
  size_t key_bytes, query_bytes;
  size_t token_stride, head_stride, selectedkv;
  size_t query_stride, key_row_bytes, query_row_bytes;
  unsigned dim, heads, tokens, kv_heads;
  shared_rvv_dot_fn dot;
  uint64_t callbacks, dots;
} shared_rvv_qk_context_t;

static inline int shared_rvv_qk_span(size_t count, size_t stride,
    size_t row, size_t *span) {
  if (!count || !row || (count > 1 && stride > (SIZE_MAX-row)/(count-1)))
    return 0;
  *span = (count-1)*stride + row;
  return 1;
}

static inline int shared_rvv_qk_address(const void *p, size_t bytes) {
  return p && bytes && bytes <= UINTPTR_MAX-(uintptr_t)p;
}

static inline int shared_rvv_qk_overlap(const void *a, size_t na,
    const void *b, size_t nb) {
  return (uintptr_t)a < (uintptr_t)b+nb && (uintptr_t)b < (uintptr_t)a+na;
}

/* AKV callback ABI: score_stride is in float elements; all context strides
 * are bytes. scores describes a writable allocation covering the requested
 * strided rectangle. Backings and context must remain valid and disjoint;
 * dot must obey the scalar-output ABI and not modify its inputs or this context.
 * Invalid requests leave scores AND counters unchanged, with no dot invocation.
 * This is callback-local preflight, not online-plan admission: online.h may
 * initialize output before invoking its callback, so callers must admit the
 * complete plan before entering either online schedule. */
static inline int shared_rvv_qk(void *opaque, unsigned first_head,
    unsigned heads, unsigned first_token, unsigned tokens,
    float *scores, size_t score_stride) {
  shared_rvv_qk_context_t *c = (shared_rvv_qk_context_t *)opaque;
  size_t key_tokens, key_span, query_span, score_elements;
  if (!c || !c->dot || !c->dim || c->dim > AKV_QUANT_MAX_DIM || c->dim%32 ||
      !c->heads || c->heads > AKV_QUANT_MAX_HEADS ||
      !c->tokens || c->tokens > AKV_QUANT_MAX_TOKENS ||
      !c->kv_heads || c->selectedkv >= c->kv_heads ||
      !heads || first_head >= c->heads || heads > c->heads-first_head ||
      !tokens || tokens > AKV_QUANT_TILE || first_token >= c->tokens ||
      tokens > c->tokens-first_token || score_stride < tokens ||
      c->query_row_bytes != (size_t)c->dim/32*34 ||
      (c->key_row_bytes != (size_t)c->dim/32*34 &&
       c->key_row_bytes != (size_t)c->dim/32*18) ||
      c->token_stride < c->key_row_bytes ||
      (c->kv_heads > 1 && c->head_stride < c->key_row_bytes) ||
      c->query_stride < c->query_row_bytes ||
      !shared_rvv_qk_span(c->tokens,c->token_stride,c->key_row_bytes,&key_tokens) ||
      !shared_rvv_qk_span(c->kv_heads,c->head_stride,key_tokens,&key_span) ||
      !shared_rvv_qk_span(c->heads,c->query_stride,c->query_row_bytes,&query_span) ||
      key_span > c->key_bytes || query_span > c->query_bytes ||
      !shared_rvv_qk_span(heads,score_stride,tokens,&score_elements) ||
      score_elements > SIZE_MAX/sizeof(float) ||
      !shared_rvv_qk_address(c->key,c->key_bytes) ||
      !shared_rvv_qk_address(c->query,c->query_bytes) ||
      !shared_rvv_qk_address(scores,score_elements*sizeof(float)) ||
      !shared_rvv_qk_address(c,sizeof(*c)) ||
      (uintptr_t)scores % _Alignof(float) ||
      c->callbacks == UINT64_MAX || c->dots > UINT64_MAX-(uint64_t)heads*tokens)
    return AKV_QUANT_BAD_ARGUMENT;
  const size_t score_bytes = score_elements*sizeof(float);
  if (shared_rvv_qk_overlap(scores,score_bytes,c->key,c->key_bytes) ||
      shared_rvv_qk_overlap(scores,score_bytes,c->query,c->query_bytes) ||
      shared_rvv_qk_overlap(scores,score_bytes,c,sizeof(*c)))
    return AKV_QUANT_BAD_ARGUMENT;

  ++c->callbacks;
  for (unsigned h = 0; h < heads; ++h) {
    const unsigned char *q = (const unsigned char *)c->query +
        (first_head+h)*c->query_stride;
    for (unsigned t = 0; t < tokens; ++t) {
      const unsigned char *k = (const unsigned char *)c->key +
          c->selectedkv*c->head_stride + (first_token+t)*c->token_stride;
      c->dot((int)c->dim,scores+h*score_stride+t,0,k,0,q,0,1);
      ++c->dots;
    }
  }
  return AKV_QUANT_OK;
}

#endif
