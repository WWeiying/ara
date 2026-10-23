#ifndef AKV_REFILL_SCHEDULE_H_
#define AKV_REFILL_SCHEDULE_H_

#include "../include/akv/akv.h"

/* Moving a read-only REFILL before accumulator stores is valid only when
 * those stores cannot change its K/V inputs. Source inputs must remain stable
 * for the call, as required by the Attention execution contract. */
static inline int akv_refill_workspace_disjoint(
    const akv_descriptor_t *descriptor, const void *workspace, size_t bytes) {
  if (!workspace || bytes == 0 ||
      !akv_v2_descriptor_is_valid(descriptor) ||
      descriptor->q_rows != AKV_ATTENTION_KERNEL_Q_ROWS ||
      descriptor->head_dim != AKV_HEAD_DIM_128 ||
      descriptor->kv_length <= AKV_V2_TILE_TOKENS)
    return 0;
  const uint64_t start = (uint64_t)(uintptr_t)workspace;
  if ((uint64_t)bytes > UINT64_MAX - start) return 0;
  const uint64_t end = start + (uint64_t)bytes;
  const uint64_t bases[2] = {descriptor->k_base, descriptor->v_base};
  const uint32_t strides[2] = {descriptor->k_token_stride_bytes,
                               descriptor->v_token_stride_bytes};
  const uint64_t row_bytes = (uint64_t)descriptor->head_dim * sizeof(uint16_t);
  for (unsigned stream = 0; stream < 2; ++stream) {
    const uint64_t last = (uint64_t)(descriptor->kv_length - 1u) * strides[stream];
    if (last > UINT64_MAX - row_bytes) return 0;
    const uint64_t span = last + row_bytes;
    if (bases[stream] > UINT64_MAX - span) return 0;
    if (start < bases[stream] + span && bases[stream] < end) return 0;
  }
  return 1;
}

#endif
