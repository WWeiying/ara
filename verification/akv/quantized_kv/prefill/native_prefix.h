#ifndef QUANT_PREFILL_NATIVE_PREFIX_H
#define QUANT_PREFILL_NATIVE_PREFIX_H

#include "software/akv/experimental/quantized_kv/native.h"
#include "prefix_schedule.h"

/* Internal, pre-admitted callback bridge. No GGML admission is implied.
 * Commands are synchronous and may consume activation only until return. */
typedef struct {
  akv_quant_native_context_t core;
  const unsigned *visible;
  unsigned alignment_copies;
  unsigned char aligned_query[4 * (AKV_QUANT_MAX_DIM / 32u) * 34u]
      __attribute__((aligned(64)));
} quant_prefill_native_context_t;

static inline qbs_status_t quant_prefill_aligned_execute(void *opaque,
    const qbs_descriptor_t *descriptor, unsigned rows, const void *activation,
    float *output, size_t stride, unsigned tokens, int segmented) {
  quant_prefill_native_context_t *c = opaque;
  const size_t row_bytes = c->core.selection->query_quant_row_bytes;
  if (!rows || rows > 4 || !row_bytes ||
      row_bytes > sizeof(c->aligned_query) / rows) return QBS_STATUS_BAD_ARGUMENT;
  if ((uintptr_t)activation & 3u) {
    memcpy(c->aligned_query, activation, rows * row_bytes);
    activation = c->aligned_query;
    ++c->alignment_copies;
  }
  const akv_quant_native_bindings_t *b = c->core.bindings;
  return b->execute(b->executor_context, descriptor, rows, activation,
                    output, stride, tokens, segmented);
}

static inline int quant_prefill_native_qk(void *opaque, unsigned first,
    unsigned rows, unsigned token, unsigned tokens, float *out, size_t stride) {
  quant_prefill_native_context_t *c = opaque;
  if (!c->visible || !rows || rows > 4 ||
      first > c->core.selection->group_heads ||
      rows > c->core.selection->group_heads - first) return 1;
  for (unsigned row = first; row < first + rows; ++row)
    if (token >= c->visible[row] || tokens > c->visible[row] - token) return 1;
  akv_quant_native_bindings_t bindings = *c->core.bindings;
  bindings.execute = quant_prefill_aligned_execute;
  bindings.executor_context = c;
  akv_quant_native_context_t core = c->core;
  core.bindings = &bindings;
  return akv_quant_native_qk(&core, first, rows, token, tokens, out, stride);
}

static inline int quant_prefill_native_value(void *opaque, unsigned token,
                                             float *out, unsigned dim) {
  quant_prefill_native_context_t *c = opaque;
  return akv_quant_native_value(&c->core, token, out, dim);
}
#endif
