#ifndef QUANT_PREFILL_PREFIX_SCHEDULE_H
#define QUANT_PREFILL_PREFIX_SCHEDULE_H

#include "software/akv/experimental/quantized_kv/online.h"

/* Experimental internal kernel: rows belong to one KV head; all buffers and
 * callbacks must already satisfy admission/ownership rules. Not a GGML API.
 * Each row has a positive visible prefix. Never issue QK for masked positions.
 * After output initialization, callback errors are terminal, not fallback. */
static inline int quant_prefill_prefix_schedule(const akv_quant_online_plan_t *p,
    const unsigned *visible, float *output, size_t stride,
    akv_quant_online_workspace_t *w) {
  if (!visible || !akv_quant_online_valid(p, output, stride, w))
    return AKV_QUANT_BAD_ARGUMENT;
  unsigned maximum = 0;
  for (unsigned row = 0; row < p->heads; ++row) {
    if (!visible[row] || visible[row] > p->tokens) return AKV_QUANT_BAD_ARGUMENT;
    if (visible[row] > maximum) maximum = visible[row];
  }
  akv_quant_online_init(p, output, stride, w);
  for (unsigned first = 0; first < maximum; first += AKV_QUANT_TILE) {
    unsigned lengths[AKV_QUANT_MAX_HEADS];
    unsigned tokens = maximum - first;
    if (tokens > AKV_QUANT_TILE) tokens = AKV_QUANT_TILE;
    for (unsigned row = 0; row < p->heads; ++row) {
      unsigned n = visible[row] > first ? visible[row] - first : 0;
      lengths[row] = n < tokens ? n : tokens;
    }
    for (unsigned row = 0; row < p->heads;) {
      if (!lengths[row]) { ++row; continue; }
      unsigned end = row + 1;
      while (end < p->heads && lengths[end] == lengths[row]) ++end;
      while (row < end) {
        const unsigned left = end - row;
        const unsigned group = left >= 4 ? 4 : left >= 2 ? 2 : 1;
        if (p->qk(p->context, row, group, first, lengths[row],
                  &w->score[row][0], AKV_QUANT_TILE)) return AKV_QUANT_QK_FAILED;
        row += group;
      }
    }
    for (unsigned token = 0; token < tokens; ++token) {
      if (p->value(p->context, first + token, w->value, p->dim))
        return AKV_QUANT_VALUE_FAILED;
      for (unsigned row = 0; row < p->heads; ++row)
        if (token < lengths[row])
          akv_quant_online_step(p, row, w->score[row][token], w->value,
                                output + row * stride, w);
    }
  }
  akv_quant_online_finish(p, output, stride, w);
  return AKV_QUANT_OK;
}

#endif
