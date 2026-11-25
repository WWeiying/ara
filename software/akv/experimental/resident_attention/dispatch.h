#ifndef AKV_EXPERIMENTAL_RESIDENT_ATTENTION_DISPATCH_H
#define AKV_EXPERIMENTAL_RESIDENT_ATTENTION_DISPATCH_H

#include "admission.h"

typedef struct {
  uint32_t query_base;
  uint32_t heads;
  uint64_t qk_control;
  uint64_t pv_control;
} akv_resident_attention_pair_t;

typedef struct {
  uint32_t tile_start;
  uint32_t tokens;
  uint32_t head_dim;
  uint32_t pair_count;
  akv_resident_attention_pair_t pairs[(AKV_MAX_Q_ROWS + 1u) / 2u];
} akv_resident_attention_tile_t;

/* Pure mapping, NOT an executor. selected is the frozen preflight result;
 * descriptor must be the same immutable, admitted local group loaded by FULL.
 * There is no global head offset: query_base restarts at zero for every group
 * and tile. REFILL changes K/V, not the resident queries. Caller must ensure the
 * actual resident D/T/group match this map; this function cannot inspect them.
 *
 * Execute all QK pairs into workspace->score[pair.query_base], then the existing
 * scale/mask/online softmax once, then all PV pairs using that row's score,
 * accumulator and old_scale. Preserve the existing RNE F16 preparation/rescale
 * and final normalization, including flags; do not run PV before softmax or
 * advance REFILL until all pairs finish. H=1 is resident too, not a retry into
 * the native generic tail. No payload pointers, VRF imports or CSR changes here.
 *
 * A failed map leaves *out untouched and issues nothing. It is NOT permission
 * to fall back after FULL or earlier work: propagate a terminal error and use
 * the owner's cleanup policy. Validate all groups before starting the call.
 */
/* Internal mapper: descriptor and tile bounds must already be checked in this
 * call. The public wrapper below remains the checked standalone interface. */
static inline akv_status_t akv_resident_attention_map_validated_tile(
    const akv_descriptor_t *descriptor,
    uint32_t tile_start, akv_resident_attention_tile_t *out) {
  akv_resident_attention_tile_t tile = {0};
  tile.tile_start = tile_start;
  tile.tokens = akv_v2_tile_length(descriptor->kv_length, tile_start);
  tile.head_dim = descriptor->head_dim;
  for (uint32_t row = 0u; row < descriptor->q_rows; row += 2u) {
    akv_resident_attention_pair_t *pair = &tile.pairs[tile.pair_count++];
    pair->query_base = row;
    pair->heads = descriptor->q_rows - row >= 2u ? 2u : 1u;
    pair->qk_control = akv_resident_qk_control(
        tile.tokens, pair->heads, tile.head_dim, row);
    pair->pv_control = akv_resident_pv_control(
        tile.tokens, pair->heads, tile.head_dim);
    if (pair->qk_control == UINT64_MAX || pair->pv_control == UINT64_MAX)
      return AKV_STATUS_RANGE;
  }
  *out = tile;
  return AKV_STATUS_OK;
}

static inline akv_status_t akv_resident_attention_dispatch_plan(
    akv_resident_attention_route_t selected, const akv_descriptor_t *descriptor,
    uint32_t tile_start, akv_resident_attention_tile_t *out) {
  if (out == NULL || selected != AKV_RESIDENT_USE_SHARED ||
      !akv_v2_descriptor_is_valid(descriptor))
    return AKV_STATUS_BAD_ARGUMENT;
  if (tile_start % AKV_V2_TILE_TOKENS != 0u ||
      tile_start >= descriptor->kv_length)
    return AKV_STATUS_RANGE;
  return akv_resident_attention_map_validated_tile(descriptor, tile_start, out);
}

#endif
