#ifndef AKV_RESIDENT_FEATURES_V2_ADMISSION_H
#define AKV_RESIDENT_FEATURES_V2_ADMISSION_H

#include "../admission.h"
#include "../../../include/akv/akv_features.h"

enum {
  AKV_RESIDENT_FEATURES_V2_ABI_VERSION = 2,
  AKV_RESIDENT_FEATURES_V2_NATIVE_SCORE_ORDER = 1,
  AKV_RESIDENT_FEATURES_V2_DECODE_HEAD_ROWS = 1,
};

/* Versioned software policy, not capability advertising or a new instruction.
 * A valid options object with requested=0 keeps the original native policy.
 * All other availability assertions default to zero. No plain-score assertion
 * is made: the existing native transform remains responsible for all features.
 */
typedef struct {
  uint32_t abi_version;
  uint32_t struct_bytes;
  uint32_t score_policy;
  uint32_t row_meaning;
  uint32_t query_tokens;
  uint32_t feature_rows;
  unsigned requested;
  unsigned validated_available;
  unsigned platform_admitted;
  unsigned whole_call_owned;
  unsigned refill_overlap;
  uintptr_t vlenb;
  unsigned frm;
  uintptr_t vstart;
} akv_resident_features_v2_options_t;

/* Features already belong to this Decode group. Arrays start at local head 0;
 * positions are absolute and are never offset by the resident query-base.
 * Existing validation checks every used array element and key-position range.
 * Prefill semantics are not executable through this entry, even on fallback.
 */
static inline akv_status_t akv_resident_features_v2_contract(
    const akv_attention_plan_t *plan, const akv_attention_features_t *features,
    const akv_resident_features_v2_options_t *options) {
  if (plan == NULL || options == NULL ||
      ((uintptr_t)plan & (AKV_DESCRIPTOR_BYTES - 1u)) != 0u ||
      options->abi_version != AKV_RESIDENT_FEATURES_V2_ABI_VERSION ||
      options->struct_bytes != sizeof(*options) ||
      options->score_policy != AKV_RESIDENT_FEATURES_V2_NATIVE_SCORE_ORDER ||
      options->feature_rows == 0u || options->feature_rows > AKV_MAX_Q_ROWS ||
      options->feature_rows != plan->descriptor.q_rows)
    return AKV_STATUS_BAD_ARGUMENT;
  if (options->row_meaning != AKV_RESIDENT_FEATURES_V2_DECODE_HEAD_ROWS ||
      options->query_tokens != 1u)
    return AKV_STATUS_RUNTIME_UNAVAILABLE;
  return akv_attention_features_validate(features, options->feature_rows,
                                         plan->descriptor.kv_length);
}

/* Preflight only. KEEP_NATIVE preserves explicit/auto selection, features and
 * overlap; it cannot make an invalid plan executable. NO_RETRY applies across
 * the caller's entire operation, not merely the current group or tile.
 */
static inline akv_resident_attention_route_t akv_resident_features_v2_select(
    const akv_device_t *device, const akv_attention_plan_t *plan,
    const akv_attention_features_t *features,
    const akv_resident_features_v2_options_t *options,
    unsigned execution_started) {
  if (execution_started != 0u) return AKV_RESIDENT_NO_RETRY;
  if (device == NULL ||
      akv_resident_features_v2_contract(plan, features, options) != AKV_STATUS_OK ||
      options->requested != 1u || options->validated_available != 1u ||
      options->platform_admitted != 1u || options->whole_call_owned != 1u ||
      options->refill_overlap != 0u || options->vlenb != AKV_RESIDENT_QK_VLEN_BITS / 8u ||
      options->frm != 0u || options->vstart != 0u ||
      !akv_attention_plan_v2_is_valid(plan) || plan->d_segment_count != 1u)
    return AKV_RESIDENT_KEEP_NATIVE;

  const akv_capabilities_t *caps = &device->capabilities;
  const uint32_t dim = plan->descriptor.head_dim;
  if (!caps->valid || !caps->enabled || !caps->f16_payload || !caps->context_count ||
      caps->max_q_rows < plan->descriptor.q_rows || caps->max_q_rows > AKV_MAX_Q_ROWS ||
      !caps->token_axis_valid || !caps->token_axis_enabled || !caps->token_axis_tail ||
      !caps->token_axis_row_view || caps->token_axis_tile_tokens != AKV_V2_TILE_TOKENS ||
      !(dim == AKV_HEAD_DIM_64 ? caps->head_dim_64 :
        dim == AKV_HEAD_DIM_96 ? caps->token_axis_d_axis_tail :
        dim == AKV_HEAD_DIM_128 ? caps->head_dim_128 : 0u))
    return AKV_RESIDENT_KEEP_NATIVE;
  return AKV_RESIDENT_USE_SHARED;
}

#endif
