#ifndef AKV_EXPERIMENTAL_RESIDENT_ATTENTION_ADMISSION_H
#define AKV_EXPERIMENTAL_RESIDENT_ATTENTION_ADMISSION_H

#include "../../include/akv/akv.h"

/* All-zero options keep the existing native route. These are call-local
 * assertions, not hardware advertising bits. In particular validated_available
 * requires externally validated shared QK/PV availability; host tests inject it.
 * Neither ordinary v2 capabilities nor an individual component gate establish
 * it. The caller checks the versioned index-4 QK/PV capability and the platform
 * ownership contract before setting it. No probing happens here.
 */
typedef struct {
  unsigned requested;
  unsigned validated_available;
  /* Trap-safe native admission: four lanes, F16/F32, FS/VS enabled, eligible
   * memory and platform support. This helper cannot establish these facts. */
  unsigned platform_admitted;
  unsigned whole_call_owned; /* Exclusive context ownership through RELEASE. */
  unsigned decode_head_rows; /* Rows are heads of ONE token, not query tokens. */
  uint32_t query_tokens;     /* Must be 1, including when q_rows happens to fit. */
  unsigned plain_scores;    /* Existing feature normalization chose NULL. */
  unsigned refill_overlap; /* Initial shared schedule requires no overlap. */
  uintptr_t vlenb;
  unsigned frm;            /* RNE only; do not change the caller's rounding. */
  uintptr_t vstart;
} akv_resident_attention_options_t;

typedef enum {
  AKV_RESIDENT_KEEP_NATIVE = 0,
  AKV_RESIDENT_USE_SHARED,
  AKV_RESIDENT_NO_RETRY,
} akv_resident_attention_route_t;

/* Preflight only, before workspace/output mutation or the first FULL. The plan
 * must come from akv_attention_plan_create_v2 and remain immutable. The caller
 * still validates workspace capacity/aliasing and retains its context lock.
 *
 * KEEP_NATIVE means run the ORIGINAL selection with all its options unchanged
 * (auto/explicit paired heads, panel4, specialized GQA6, refill overlap, etc.);
 * it does not force a generic kernel or make an invalid plan executable.
 *
 * execution_started stays nonzero across every tile/group that a fallback would
 * replay. NO_RETRY forbids re-selection, partial retry and frontend fallback;
 * retain the already chosen route, or terminate on error with caller-owned
 * cleanup. A trap is not a capability probe. No numerical work/CSR writes occur.
 */
static inline int akv_resident_attention_options_admitted(
    const akv_device_t *device, const akv_attention_plan_t *plan,
    const akv_resident_attention_options_t *options) {
  if (device == NULL || plan == NULL || options == NULL ||
      options->requested != 1u || options->validated_available != 1u ||
      options->platform_admitted != 1u || options->whole_call_owned != 1u ||
      options->decode_head_rows != 1u || options->query_tokens != 1u ||
      options->plain_scores != 1u || options->refill_overlap != 0u ||
      options->vlenb != AKV_RESIDENT_QK_VLEN_BITS / 8u ||
      options->frm != 0u || options->vstart != 0u ||
      ((uintptr_t)plan & (AKV_DESCRIPTOR_BYTES - 1u)) != 0u)
    return 0;
  return 1;
}

static inline akv_resident_attention_route_t akv_resident_attention_capability_route(
    const akv_device_t *device, const akv_attention_plan_t *plan) {
  const akv_capabilities_t *caps = &device->capabilities;
  const uint32_t dim = plan->descriptor.head_dim;
  if (!caps->valid || !caps->enabled || !caps->f16_payload ||
      !caps->context_count || caps->max_q_rows < plan->descriptor.q_rows ||
      caps->max_q_rows > AKV_MAX_Q_ROWS || !caps->token_axis_valid ||
      !caps->token_axis_enabled || !caps->token_axis_tail ||
      !caps->token_axis_row_view ||
      caps->token_axis_tile_tokens != AKV_V2_TILE_TOKENS ||
      !(dim == AKV_HEAD_DIM_64 ? caps->head_dim_64 :
        dim == AKV_HEAD_DIM_96 ? caps->token_axis_d_axis_tail :
        dim == AKV_HEAD_DIM_128 ? caps->head_dim_128 : 0u))
    return AKV_RESIDENT_KEEP_NATIVE;
  return AKV_RESIDENT_USE_SHARED;
}

/* SDK-internal reuse of the immediately preceding single-segment plan check.
 * Not an entry point for unvalidated plans or a cache across calls. Keep the
 * device/options checks and the executor's live CSR check on every call. */
static inline akv_resident_attention_route_t akv_resident_attention_select_validated_plan(
    const akv_device_t *device, const akv_attention_plan_t *plan,
    const akv_resident_attention_options_t *options) {
  if (!akv_resident_attention_options_admitted(device, plan, options) ||
      plan->d_segment_count != 1u)
    return AKV_RESIDENT_KEEP_NATIVE;
  return akv_resident_attention_capability_route(device, plan);
}

/* The standalone selector retains full validation and the no-retry contract. */
static inline akv_resident_attention_route_t akv_resident_attention_select(
    const akv_device_t *device, const akv_attention_plan_t *plan,
    const akv_resident_attention_options_t *options,
    unsigned execution_started) {
  if (execution_started != 0u) return AKV_RESIDENT_NO_RETRY;
  if (!akv_resident_attention_options_admitted(device, plan, options) ||
      !akv_attention_plan_v2_is_valid(plan) || plan->d_segment_count != 1u)
    return AKV_RESIDENT_KEEP_NATIVE;
  return akv_resident_attention_capability_route(device, plan);
}

#endif
