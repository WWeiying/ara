#include "../include/akv/akv_features.h"

#include <math.h>
#include <string.h>

static int finite_f32(float value) {
  uint32_t bits;
  memcpy(&bits, &value, sizeof(bits));
  return (bits & UINT32_C(0x7f800000)) != UINT32_C(0x7f800000);
}

static float from_f16(uint16_t h) {
  const uint32_t sign = (uint32_t)(h & 0x8000u) << 16;
  uint32_t exponent = (h >> 10) & 31u;
  uint32_t fraction = h & 1023u;
  uint32_t bits;
  if (exponent == 31u) bits = sign | 0x7f800000u | (fraction << 13);
  else if (exponent) bits = sign | ((exponent + 112u) << 23) | (fraction << 13);
  else if (!fraction) bits = sign;
  else {
    unsigned shift = 0;
    while ((fraction & 1024u) == 0u) { fraction <<= 1; ++shift; }
    bits = sign | ((113u - shift) << 23) | ((fraction & 1023u) << 13);
  }
  float value;
  memcpy(&value, &bits, sizeof(value));
  return value;
}

akv_status_t akv_attention_features_validate(
    const akv_attention_features_t *f, uint32_t q_rows, uint32_t kv_length) {
  if (!f) return AKV_STATUS_OK;
  if (!q_rows || q_rows > AKV_MAX_Q_ROWS || !kv_length ||
      !finite_f32(f->softcap) || f->softcap < 0.0f ||
      f->mask_scale_enabled > 1u || f->position_bias_enabled > 1u ||
      f->sinks_enabled > 1u || f->window_enabled > 1u ||
      f->key_position_base > UINT64_MAX - (kv_length - 1u))
    return AKV_STATUS_BAD_ARGUMENT;
  for (uint32_t head = 0; head < q_rows; ++head) {
    if ((f->mask_scale_enabled &&
         (!finite_f32(f->mask_scale[head]) || f->mask_scale[head] <= 0.0f)) ||
        (f->position_bias_enabled && !finite_f32(f->position_slope[head])) ||
        (f->sinks_enabled && !finite_f32(f->sinks[head])))
      return AKV_STATUS_BAD_ARGUMENT;
  }
  return AKV_STATUS_OK;
}

float akv_attention_score_transform(float dot, float scale, uint16_t mask,
                                     uint32_t head, uint32_t key_index,
                                     const akv_attention_features_t *f) {
  /* Masked positions remain excluded even when their dot overflows. */
  if (mask == UINT16_C(0xfc00)) return -INFINITY;
  volatile float scaled = dot * scale;
  float result = scaled;
  if (f) {
    const uint64_t position = f->key_position_base + key_index;
    if (f->window_enabled &&
        ((position < f->query_position &&
          f->query_position - position > f->window_left) ||
         (position > f->query_position &&
          position - f->query_position > f->window_right)))
      return -INFINITY;
    if (f->softcap != 0.0f)
      result = f->softcap * tanhf(result / f->softcap);
    if (f->position_bias_enabled) {
      const float distance = position >= f->query_position
          ? (float)(position - f->query_position)
          : -(float)(f->query_position - position);
      volatile float bias = f->position_slope[head] * distance;
      result += bias;
    }
  }
  volatile float bias = from_f16(mask) *
      ((f && f->mask_scale_enabled) ? f->mask_scale[head] : 1.0f);
  return result + bias;
}

static float reference_score(const akv_attention_plan_t *p,
                              const akv_attention_features_t *f,
                              uint32_t head, uint32_t token) {
  const uint16_t *q = (const uint16_t *)(uintptr_t)(p->descriptor.q_base +
      (size_t)head * p->descriptor.q_row_stride_bytes);
  const uint16_t *k = (const uint16_t *)(uintptr_t)(p->descriptor.k_base +
      (size_t)token * p->descriptor.k_token_stride_bytes);
  float dot = 0.0f;
  for (uint32_t d = 0; d < p->logical_head_dim; ++d)
    dot = fmaf(from_f16(q[d]), from_f16(k[d]), dot);
  return akv_attention_score_transform(dot, p->scale, p->mask[token],
                                        head, token, f);
}

akv_status_t akv_attention_execute_v2_with_features_reference(
    const akv_attention_plan_t *p, const akv_attention_features_t *f) {
  if (!akv_attention_plan_v2_is_valid(p) ||
      akv_attention_features_validate(f, p->descriptor.q_rows,
                                      p->descriptor.kv_length) != AKV_STATUS_OK)
    return AKV_STATUS_BAD_ARGUMENT;
  for (uint32_t token = 0; token < p->descriptor.kv_length; ++token)
    if ((p->mask[token] & 0x7c00u) == 0x7c00u && p->mask[token] != 0xfc00u)
      return AKV_STATUS_BAD_ARGUMENT;
  const uint64_t value_base = p->d_segment_count == 2u
      ? p->value_descriptor.k_base : p->descriptor.v_base;
  const uint32_t value_stride = p->d_segment_count == 2u
      ? p->value_descriptor.k_token_stride_bytes : p->descriptor.v_token_stride_bytes;
  for (uint32_t h = 0; h < p->descriptor.q_rows; ++h) {
    float maximum = f && f->sinks_enabled ? f->sinks[h] : -INFINITY;
    for (uint32_t t = 0; t < p->descriptor.kv_length; ++t) {
      const float score = reference_score(p, f, h, t);
      if (score > maximum) maximum = score;
    }
    float sum = f && f->sinks_enabled ? expf(f->sinks[h] - maximum) : 0.0f;
    float accumulator[AKV_HEAD_DIM_256] = {0};
    if (maximum != -INFINITY) {
      for (uint32_t t = 0; t < p->descriptor.kv_length; ++t) {
        const float score = reference_score(p, f, h, t);
        if (score == -INFINITY) continue;
        const float weight = expf(score - maximum);
        sum += weight;
        const uint16_t *v = (const uint16_t *)(uintptr_t)(value_base +
            (size_t)t * value_stride);
        for (uint32_t d = 0; d < p->logical_head_dim; ++d)
          accumulator[d] = fmaf(weight, from_f16(v[d]), accumulator[d]);
      }
    }
    float *out = (float *)((char *)p->output + h * p->output_row_stride_bytes);
    for (uint32_t d = 0; d < p->logical_head_dim; ++d)
      out[d] = sum == 0.0f ? 0.0f : accumulator[d] / sum;
  }
  return AKV_STATUS_OK;
}
