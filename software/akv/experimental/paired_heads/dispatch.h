#ifndef AKV_EXPERIMENTAL_PAIR_DISPATCH_H
#define AKV_EXPERIMENTAL_PAIR_DISPATCH_H

#include <stddef.h>
#include <stdint.h>

extern void akv_v2_compute_scores_f16_generic(
    const uint16_t *, float *, uint32_t, size_t, uint32_t, uint32_t);
extern void akv_v2_update_outputs_f16_generic(
    const float *, uint16_t *, const float *, uint32_t, uint32_t, uint32_t);
extern void akv_experimental_qk_f16_pair_panel4(
    const uint16_t *, float *, uint32_t, size_t, uint32_t);
extern void akv_experimental_pv_f16_pair(
    const float *, uint16_t *, const float *, uint32_t, uint32_t);

/* Caller validates the plan and snapshots admission before FULL. These helpers
 * preserve Decode workspace strides, including padding at D64 and D96. */
static inline void akv_pair_qk_f16_dispatch(
    int admitted, const uint16_t *query, float *score, uint32_t tokens,
    size_t query_stride, uint32_t heads, uint32_t dim) {
  if (!admitted) {
    akv_v2_compute_scores_f16_generic(
        query, score, tokens, query_stride, heads, dim);
    return;
  }
  uint32_t head = 0;
  for (; head + 1 < heads; head += 2)
    akv_experimental_qk_f16_pair_panel4(
        (const uint16_t *)((const char *)query + head * query_stride),
        score + head * 64, tokens, query_stride, dim);
  if (head < heads)
    akv_v2_compute_scores_f16_generic(
        (const uint16_t *)((const char *)query + head * query_stride),
        score + head * 64, tokens, query_stride, 1, dim);
}

static inline void akv_pair_pv_f16_dispatch(
    int admitted, const float *score, uint16_t *accumulator,
    const float *old_scale, uint32_t tokens, uint32_t heads, uint32_t dim) {
  if (!admitted) {
    akv_v2_update_outputs_f16_generic(
        score, accumulator, old_scale, tokens, heads, dim);
    return;
  }
  uint32_t head = 0;
  for (; head + 1 < heads; head += 2)
    akv_experimental_pv_f16_pair(
        score + head * 64, accumulator + head * 256,
        old_scale + head, tokens, dim);
  if (head < heads)
    akv_v2_update_outputs_f16_generic(
        score + head * 64, accumulator + head * 256,
        old_scale + head, tokens, 1, dim);
}

#endif
