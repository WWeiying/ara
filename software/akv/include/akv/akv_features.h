#ifndef AKV_FEATURES_H_
#define AKV_FEATURES_H_

#include "akv.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Optional software/RVV score operations; no new hardware command or SRAM.
 * Order: scale, softcap, position bias, additive mask, window exclusion.
 * A sink is one extra score in the denominator with an all-zero Value.
 * All positions are absolute token positions, including in a segmented call.
 */
typedef struct {
  float softcap;
  uint8_t mask_scale_enabled;
  uint8_t position_bias_enabled;
  uint8_t sinks_enabled;
  uint8_t window_enabled;
  float mask_scale[AKV_MAX_Q_ROWS];
  float position_slope[AKV_MAX_Q_ROWS];
  float sinks[AKV_MAX_Q_ROWS];
  uint64_t key_position_base;
  uint64_t query_position;
  uint32_t window_left;
  uint32_t window_right;
} akv_attention_features_t;

akv_status_t akv_attention_features_validate(
    const akv_attention_features_t *features, uint32_t q_rows,
    uint32_t kv_length);
/* Call after validation. Mask holes and additive biases must retain the
 * feature path, including its masked-overflow handling. */
int akv_attention_can_use_plain_scores(
    const akv_attention_features_t *features, const uint16_t *mask,
    uint32_t kv_length);
float akv_attention_score_transform(float dot, float scale, uint16_t mask,
                                     uint32_t head, uint32_t key_index,
                                     const akv_attention_features_t *features);
akv_status_t akv_attention_execute_v2_with_features_native(
    const akv_attention_plan_t *plan, akv_attention_v2_workspace_t *workspace,
    const akv_attention_features_t *features);

/* Mathematical F32 oracle. Unlike native execution, it does not round the
 * Value accumulator to F16 or approximate exp with the RVV polynomial.
 * It is for tolerance-based functional checking, not bit/cycle prediction.
 */
akv_status_t akv_attention_execute_v2_with_features_reference(
    const akv_attention_plan_t *plan,
    const akv_attention_features_t *features);

#ifdef __cplusplus
}
#endif
#endif
