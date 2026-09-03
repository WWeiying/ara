#include "akv_prefill_internal.h"

#include <math.h>
#include <stdint.h>
#include <string.h>

typedef struct {
  uintptr_t first;
  uintptr_t last;
} byte_range_t;

static int finite_positive_f32(float value) {
  uint32_t bits;
  memcpy(&bits, &value, sizeof(bits));
  return (bits >> 31) == 0u && (bits & UINT32_C(0x7fffffff)) != 0u &&
         (bits & UINT32_C(0x7f800000)) != UINT32_C(0x7f800000);
}

static float negative_infinity_f32(void) {
  const uint32_t bits = UINT32_C(0xff800000);
  float value;
  memcpy(&value, &bits, sizeof(value));
  return value;
}

static int is_negative_infinity_f32(float value) {
  uint32_t bits;
  memcpy(&bits, &value, sizeof(bits));
  return bits == UINT32_C(0xff800000);
}

static int finite_f16_bits(uint16_t value) {
  return (value & UINT16_C(0x7c00)) != UINT16_C(0x7c00);
}

static int multiply_size(size_t lhs, size_t rhs, size_t *product) {
  return !__builtin_mul_overflow(lhs, rhs, product);
}

static int resolve_stride(uint32_t requested, size_t canonical,
                          uint32_t *resolved) {
  const size_t value = requested == 0u ? canonical : requested;
  if (value == 0u || value > UINT32_MAX) return 0;
  *resolved = (uint32_t)value;
  return 1;
}

/* Returns -1 for arithmetic overflow, 0 for overlapping rows, and 1 on OK. */
static int matrix_layout_span(size_t row_bytes, uint32_t first_count,
                              uint32_t first_stride, uint32_t second_count,
                              uint32_t second_stride, size_t *span) {
  size_t first_offset;
  size_t second_offset;
  size_t first_extent;
  size_t second_extent;
  size_t last_offset;
  if (__builtin_mul_overflow((size_t)(first_count - 1u), first_stride,
                             &first_offset) ||
      __builtin_mul_overflow((size_t)(second_count - 1u), second_stride,
                             &second_offset) ||
      __builtin_add_overflow(first_offset, row_bytes, &first_extent) ||
      __builtin_add_overflow(second_offset, row_bytes, &second_extent) ||
      __builtin_add_overflow(first_offset, second_offset, &last_offset) ||
      __builtin_add_overflow(last_offset, row_bytes, span))
    return -1;
  if (!((first_stride >= row_bytes && second_stride >= first_extent) ||
        (second_stride >= row_bytes && first_stride >= second_extent)))
    return 0;
  return 1;
}

/* Returns -1 for arithmetic overflow, 0 for overlapping rows, and 1 on OK. */
static int linear_layout_span(size_t row_bytes, uint32_t count,
                              uint32_t stride, size_t *span) {
  size_t last_offset;
  if (__builtin_mul_overflow((size_t)(count - 1u), stride, &last_offset) ||
      __builtin_add_overflow(last_offset, row_bytes, span))
    return -1;
  return count == 1u || stride >= row_bytes;
}

static int byte_range(const void *base, size_t bytes, byte_range_t *range) {
  if (base == NULL || bytes == 0u ||
      __builtin_add_overflow((uintptr_t)base, bytes - 1u, &range->last))
    return 0;
  range->first = (uintptr_t)base;
  return 1;
}

static int ranges_overlap(byte_range_t lhs, byte_range_t rhs) {
  return lhs.first <= rhs.last && rhs.first <= lhs.last;
}

akv_status_t akv_attention_v2_prefill_validate(
    const akv_device_t *device,
    const akv_attention_v2_prefill_problem_t *problem,
    const akv_attention_v2_prefill_workspace_t *workspace,
    uint32_t *past_tokens, uint32_t *maximum_prefix,
    akv_attention_v2_prefill_layout_t *layout) {
  if (device == NULL || problem == NULL || workspace == NULL ||
      past_tokens == NULL || maximum_prefix == NULL || layout == NULL ||
      problem->query == NULL || problem->key == NULL ||
      problem->value == NULL || problem->mask == NULL ||
      problem->output == NULL || !finite_positive_f32(problem->scale))
    return AKV_STATUS_BAD_ARGUMENT;

  if (((uintptr_t)workspace & (AKV_DESCRIPTOR_BYTES - 1u)) != 0u ||
      (((uintptr_t)problem->query | (uintptr_t)problem->output) &
       (sizeof(float) - 1u)) != 0u ||
      (((uintptr_t)problem->key | (uintptr_t)problem->value) &
       ((UINT64_C(1) << AKV_V2_PAYLOAD_ALIGNMENT_LOG2) - 1u)) != 0u ||
      ((uintptr_t)problem->mask & (sizeof(uint16_t) - 1u)) != 0u)
    return AKV_STATUS_LAYOUT;

  const akv_capabilities_t *const caps = &device->capabilities;
  if (!caps->valid || !caps->enabled || !caps->token_axis_valid ||
      !caps->token_axis_enabled || !caps->f16_payload ||
      caps->context_count == 0u ||
      caps->token_axis_tile_tokens != AKV_V2_TILE_TOKENS)
    return AKV_STATUS_CAPABILITY;

  if (problem->query_tokens <= 1u || problem->query_tokens > UINT16_MAX ||
      problem->query_heads == 0u || problem->kv_heads == 0u ||
      problem->kv_capacity == 0u || problem->kv_capacity > UINT16_MAX ||
      problem->query_heads % problem->kv_heads != 0u)
    return AKV_STATUS_SHAPE;
  const uint32_t q_rows = problem->query_heads / problem->kv_heads;
  const int head_dim_capable =
      problem->head_dim == AKV_HEAD_DIM_64
          ? caps->head_dim_64
          : (problem->head_dim == AKV_HEAD_DIM_96
                 ? caps->token_axis_d_axis_tail
                 : (problem->head_dim == AKV_HEAD_DIM_128
                        ? caps->head_dim_128
                        : 0));
  if (!head_dim_capable || q_rows == 0u || q_rows > caps->max_q_rows ||
      q_rows > AKV_MAX_Q_ROWS)
    return AKV_STATUS_SHAPE;

  size_t query_row_bytes;
  size_t kv_row_bytes;
  size_t mask_row_bytes;
  size_t canonical_query_head_stride;
  size_t canonical_kv_head_stride;
  size_t canonical_output_token_stride;
  if (!multiply_size(problem->head_dim, sizeof(float), &query_row_bytes) ||
      !multiply_size(problem->head_dim, sizeof(uint16_t), &kv_row_bytes) ||
      !multiply_size(problem->kv_capacity, sizeof(uint16_t),
                     &mask_row_bytes) ||
      !multiply_size(query_row_bytes, problem->query_tokens,
                     &canonical_query_head_stride) ||
      !multiply_size(kv_row_bytes, problem->kv_capacity,
                     &canonical_kv_head_stride) ||
      !multiply_size(query_row_bytes, problem->query_heads,
                     &canonical_output_token_stride) ||
      !resolve_stride(problem->query_token_stride_bytes, query_row_bytes,
                      &layout->query_token_stride_bytes) ||
      !resolve_stride(problem->query_head_stride_bytes,
                      canonical_query_head_stride,
                      &layout->query_head_stride_bytes) ||
      !resolve_stride(problem->key_token_stride_bytes, kv_row_bytes,
                      &layout->key_token_stride_bytes) ||
      !resolve_stride(problem->key_head_stride_bytes,
                      canonical_kv_head_stride,
                      &layout->key_head_stride_bytes) ||
      !resolve_stride(problem->value_token_stride_bytes, kv_row_bytes,
                      &layout->value_token_stride_bytes) ||
      !resolve_stride(problem->value_head_stride_bytes,
                      canonical_kv_head_stride,
                      &layout->value_head_stride_bytes) ||
      !resolve_stride(problem->mask_token_stride_bytes, mask_row_bytes,
                      &layout->mask_token_stride_bytes) ||
      !resolve_stride(problem->output_token_stride_bytes,
                      canonical_output_token_stride,
                      &layout->output_token_stride_bytes))
    return AKV_STATUS_RANGE;

  if ((layout->query_token_stride_bytes | layout->query_head_stride_bytes |
       layout->output_token_stride_bytes) & (sizeof(float) - 1u))
    return AKV_STATUS_LAYOUT;
  if ((layout->key_token_stride_bytes | layout->key_head_stride_bytes |
       layout->value_token_stride_bytes | layout->value_head_stride_bytes) &
      ((UINT32_C(1) << AKV_V2_PAYLOAD_ALIGNMENT_LOG2) - 1u))
    return AKV_STATUS_LAYOUT;
  if ((layout->mask_token_stride_bytes & (sizeof(uint16_t) - 1u)) != 0u)
    return AKV_STATUS_LAYOUT;

  size_t query_span;
  size_t key_span;
  size_t value_span;
  size_t mask_span;
  size_t output_span;
  int layout_status = matrix_layout_span(
      query_row_bytes, problem->query_tokens,
      layout->query_token_stride_bytes, problem->query_heads,
      layout->query_head_stride_bytes, &query_span);
  if (layout_status < 0) return AKV_STATUS_RANGE;
  if (layout_status == 0) return AKV_STATUS_LAYOUT;
  layout_status = matrix_layout_span(
      kv_row_bytes, problem->kv_capacity, layout->key_token_stride_bytes,
      problem->kv_heads, layout->key_head_stride_bytes, &key_span);
  if (layout_status < 0) return AKV_STATUS_RANGE;
  if (layout_status == 0) return AKV_STATUS_LAYOUT;
  layout_status = matrix_layout_span(
      kv_row_bytes, problem->kv_capacity, layout->value_token_stride_bytes,
      problem->kv_heads, layout->value_head_stride_bytes, &value_span);
  if (layout_status < 0) return AKV_STATUS_RANGE;
  if (layout_status == 0) return AKV_STATUS_LAYOUT;
  layout_status = linear_layout_span(mask_row_bytes, problem->query_tokens,
                                     layout->mask_token_stride_bytes,
                                     &mask_span);
  if (layout_status < 0) return AKV_STATUS_RANGE;
  if (layout_status == 0) return AKV_STATUS_LAYOUT;
  layout_status = matrix_layout_span(
      query_row_bytes, problem->query_heads, (uint32_t)query_row_bytes,
      problem->query_tokens, layout->output_token_stride_bytes, &output_span);
  if (layout_status < 0) return AKV_STATUS_RANGE;
  if (layout_status == 0) return AKV_STATUS_LAYOUT;

  byte_range_t query_range;
  byte_range_t key_range;
  byte_range_t value_range;
  byte_range_t mask_range;
  byte_range_t output_range;
  byte_range_t workspace_range;
  if (!byte_range(problem->query, query_span, &query_range) ||
      !byte_range(problem->key, key_span, &key_range) ||
      !byte_range(problem->value, value_span, &value_range) ||
      !byte_range(problem->mask, mask_span, &mask_range) ||
      !byte_range(problem->output, output_span, &output_range) ||
      !byte_range(workspace, sizeof(*workspace), &workspace_range))
    return AKV_STATUS_RANGE;

  const byte_range_t read_ranges[] = {
      query_range, key_range, value_range, mask_range};
  const byte_range_t write_ranges[] = {output_range, workspace_range};
  for (size_t write = 0u;
       write < sizeof(write_ranges) / sizeof(write_ranges[0]); ++write) {
    for (size_t read = 0u;
         read < sizeof(read_ranges) / sizeof(read_ranges[0]); ++read) {
      if (ranges_overlap(write_ranges[write], read_ranges[read]))
        return AKV_STATUS_ALIAS;
    }
    for (size_t other = write + 1u;
         other < sizeof(write_ranges) / sizeof(write_ranges[0]); ++other) {
      if (ranges_overlap(write_ranges[write], write_ranges[other]))
        return AKV_STATUS_ALIAS;
    }
  }

  const uint16_t *first_mask = problem->mask;
  uint32_t first_prefix = 0u;
  while (first_prefix < problem->kv_capacity &&
         first_mask[first_prefix] != UINT16_C(0xfc00)) {
    if (!finite_f16_bits(first_mask[first_prefix])) return AKV_STATUS_SHAPE;
    ++first_prefix;
  }
  if (first_prefix == 0u) return AKV_STATUS_SHAPE;
  for (uint32_t sequence = first_prefix; sequence < problem->kv_capacity;
       ++sequence) {
    if (first_mask[sequence] != UINT16_C(0xfc00)) return AKV_STATUS_SHAPE;
  }
  *past_tokens = first_prefix - 1u;
  if (*past_tokens > UINT16_MAX - problem->query_tokens)
    return AKV_STATUS_SHAPE;
  *maximum_prefix = *past_tokens + problem->query_tokens;
  if (*maximum_prefix > problem->kv_capacity ||
      *maximum_prefix > UINT16_MAX)
    return AKV_STATUS_SHAPE;

  for (uint32_t token = 1u; token < problem->query_tokens; ++token) {
    const uint16_t *const token_mask = (const uint16_t *)(const void *)(
        (const char *)problem->mask +
        (size_t)token * layout->mask_token_stride_bytes);
    const uint32_t expected_prefix = *past_tokens + token + 1u;
    for (uint32_t sequence = 0u; sequence < expected_prefix; ++sequence) {
      if (!finite_f16_bits(token_mask[sequence])) return AKV_STATUS_SHAPE;
    }
    for (uint32_t sequence = expected_prefix;
         sequence < problem->kv_capacity; ++sequence) {
      if (token_mask[sequence] != UINT16_C(0xfc00)) return AKV_STATUS_SHAPE;
    }
  }
  return AKV_STATUS_OK;
}

static float f16_to_f32(uint16_t value) {
  const uint32_t sign = (uint32_t)(value & UINT16_C(0x8000)) << 16;
  uint32_t exponent = (value >> 10) & 0x1fu;
  uint32_t fraction = value & 0x3ffu;
  uint32_t bits;

  if (exponent == 0u) {
    if (fraction == 0u) {
      bits = sign;
    } else {
      uint32_t shift = 0u;
      while ((fraction & 0x400u) == 0u) {
        fraction <<= 1;
        ++shift;
      }
      fraction &= 0x3ffu;
      bits = sign | ((UINT32_C(113) - shift) << 23) | (fraction << 13);
    }
  } else if (exponent == 0x1fu) {
    bits = sign | UINT32_C(0x7f800000) | (fraction << 13);
  } else {
    bits = sign | ((exponent + UINT32_C(112)) << 23) | (fraction << 13);
  }

  float result;
  memcpy(&result, &bits, sizeof(result));
  return result;
}

static float multiply_then_add_f32(float lhs, float rhs, float addend) {
  volatile float product = lhs * rhs;
  return product + addend;
}

static uint16_t f32_to_f16(float value) {
  uint32_t bits;
  memcpy(&bits, &value, sizeof(bits));
  const uint16_t sign = (uint16_t)((bits >> 16) & UINT32_C(0x8000));
  const uint32_t exponent_bits = (bits >> 23) & 0xffu;
  uint32_t fraction = bits & UINT32_C(0x7fffff);

  if (exponent_bits == 0xffu)
    return (uint16_t)(sign | (fraction == 0u ? UINT16_C(0x7c00)
                                             : UINT16_C(0x7e00)));

  const int32_t exponent = (int32_t)exponent_bits - 127 + 15;
  if (exponent >= 31) return (uint16_t)(sign | UINT16_C(0x7c00));
  if (exponent <= 0) {
    if (exponent < -10) return sign;
    fraction |= UINT32_C(0x800000);
    const uint32_t shift = (uint32_t)(14 - exponent);
    uint32_t rounded = fraction >> shift;
    const uint32_t remainder = fraction & ((UINT32_C(1) << shift) - 1u);
    const uint32_t halfway = UINT32_C(1) << (shift - 1u);
    if (remainder > halfway || (remainder == halfway && (rounded & 1u) != 0u))
      ++rounded;
    return (uint16_t)(sign | rounded);
  }

  uint32_t rounded = fraction >> 13;
  const uint32_t remainder = fraction & UINT32_C(0x1fff);
  if (remainder > UINT32_C(0x1000) ||
      (remainder == UINT32_C(0x1000) && (rounded & 1u) != 0u))
    ++rounded;
  uint32_t half_exponent = (uint32_t)exponent;
  if (rounded == 0x400u) {
    rounded = 0u;
    ++half_exponent;
    if (half_exponent >= 31u)
      return (uint16_t)(sign | UINT16_C(0x7c00));
  }
  return (uint16_t)(sign | (uint16_t)(half_exponent << 10) |
                    (uint16_t)rounded);
}

akv_status_t akv_attention_execute_v2_prefill_reference(
    const akv_device_t *device,
    const akv_attention_v2_prefill_problem_t *problem,
    akv_attention_v2_prefill_workspace_t *workspace) {
  uint32_t past_tokens = 0u;
  uint32_t maximum_prefix = 0u;
  akv_attention_v2_prefill_layout_t layout;
  const akv_status_t validation = akv_attention_v2_prefill_validate(
      device, problem, workspace, &past_tokens, &maximum_prefix, &layout);
  if (validation != AKV_STATUS_OK) return validation;
  (void)maximum_prefix;

  const uint32_t q_rows = problem->query_heads / problem->kv_heads;
  for (uint32_t kv_head = 0u; kv_head < problem->kv_heads; ++kv_head) {
    const uint32_t first_qhead = kv_head * q_rows;
    const char *const key_base =
        (const char *)problem->key +
        (size_t)kv_head * layout.key_head_stride_bytes;
    const char *const value_base =
        (const char *)problem->value +
        (size_t)kv_head * layout.value_head_stride_bytes;

    for (uint32_t token_start = 0u; token_start < problem->query_tokens;
         token_start += AKV_PREFILL_QUERY_BLOCK_TOKENS) {
      uint32_t token_count = problem->query_tokens - token_start;
      if (token_count > AKV_PREFILL_QUERY_BLOCK_TOKENS)
        token_count = AKV_PREFILL_QUERY_BLOCK_TOKENS;

      for (uint32_t local_token = 0u; local_token < token_count;
           ++local_token) {
        const uint32_t token = token_start + local_token;
        for (uint32_t head = 0u; head < q_rows; ++head) {
          const float *const query = (const float *)(const void *)(
              (const char *)problem->query +
              (size_t)(first_qhead + head) *
                  layout.query_head_stride_bytes +
              (size_t)token * layout.query_token_stride_bytes);
          for (uint32_t dimension = 0u; dimension < problem->head_dim;
               ++dimension) {
            workspace->query[local_token][head][dimension] =
                f32_to_f16(query[dimension]);
          }
          workspace->maximum[local_token][head] = negative_infinity_f32();
          workspace->sum[local_token][head] = 0.0f;
          float *const output = (float *)(void *)(
              (char *)problem->output +
              (size_t)token * layout.output_token_stride_bytes +
              (size_t)(first_qhead + head) * problem->head_dim *
                  sizeof(float));
          memset(output, 0, (size_t)problem->head_dim * sizeof(*output));
        }
      }

      const uint32_t block_prefix = past_tokens + token_start + token_count;
      for (uint32_t tile_start = 0u; tile_start < block_prefix;
           tile_start += AKV_V2_TILE_TOKENS) {
        uint32_t tile_count = block_prefix - tile_start;
        if (tile_count > AKV_V2_TILE_TOKENS)
          tile_count = AKV_V2_TILE_TOKENS;

        for (uint32_t local_token = 0u; local_token < token_count;
             ++local_token) {
          const uint32_t token = token_start + local_token;
          const uint32_t active_prefix = past_tokens + token + 1u;
          if (active_prefix <= tile_start) continue;
          uint32_t active_tokens = active_prefix - tile_start;
          if (active_tokens > tile_count) active_tokens = tile_count;
          const uint16_t *const mask = (const uint16_t *)(const void *)(
              (const char *)problem->mask +
              (size_t)token * layout.mask_token_stride_bytes) + tile_start;

          for (uint32_t head = 0u; head < q_rows; ++head) {
            float tile_maximum = negative_infinity_f32();
            for (uint32_t sequence = 0u; sequence < active_tokens;
                 ++sequence) {
              const uint16_t *const key =
                  (const uint16_t *)(const void *)(
                      key_base + (size_t)(tile_start + sequence) *
                                     layout.key_token_stride_bytes);
              float dot = 0.0f;
              for (uint32_t dimension = 0u; dimension < problem->head_dim;
                   ++dimension) {
                dot += f16_to_f32(workspace->query[local_token][head][dimension]) *
                       f16_to_f32(key[dimension]);
              }
              const float score = multiply_then_add_f32(
                  dot, problem->scale, f16_to_f32(mask[sequence]));
              workspace->score[0][head][sequence] = score;
              if (score > tile_maximum) tile_maximum = score;
            }

            const float old_maximum = workspace->maximum[local_token][head];
            const float new_maximum =
                tile_maximum > old_maximum ? tile_maximum : old_maximum;
            const float old_scale = is_negative_infinity_f32(old_maximum)
                                        ? 0.0f
                                        : expf(old_maximum - new_maximum);
            workspace->old_scale[0][head] = old_scale;
            float tile_sum = 0.0f;
            for (uint32_t sequence = 0u; sequence < active_tokens;
                 ++sequence) {
              const float weight =
                  expf(workspace->score[0][head][sequence] - new_maximum);
              workspace->score[0][head][sequence] = weight;
              tile_sum += weight;
            }
            workspace->maximum[local_token][head] = new_maximum;
            workspace->sum[local_token][head] =
                workspace->sum[local_token][head] * old_scale + tile_sum;

            float *const output = (float *)(void *)(
                (char *)problem->output +
                (size_t)token * layout.output_token_stride_bytes +
                (size_t)(first_qhead + head) * problem->head_dim *
                    sizeof(float));
            for (uint32_t dimension = 0u; dimension < problem->head_dim;
                 ++dimension) {
              float accumulated = output[dimension] * old_scale;
              for (uint32_t sequence = 0u; sequence < active_tokens;
                   ++sequence) {
                const uint16_t *const value =
                    (const uint16_t *)(const void *)(
                        value_base + (size_t)(tile_start + sequence) *
                                         layout.value_token_stride_bytes);
                accumulated += workspace->score[0][head][sequence] *
                               f16_to_f32(value[dimension]);
              }
              output[dimension] = accumulated;
            }
          }
        }
      }

      for (uint32_t local_token = 0u; local_token < token_count;
           ++local_token) {
        const uint32_t token = token_start + local_token;
        for (uint32_t head = 0u; head < q_rows; ++head) {
          const float sum = workspace->sum[local_token][head];
          const float inverse = sum == 0.0f ? 0.0f : 1.0f / sum;
          float *const output = (float *)(void *)(
              (char *)problem->output +
              (size_t)token * layout.output_token_stride_bytes +
              (size_t)(first_qhead + head) * problem->head_dim *
                  sizeof(float));
          for (uint32_t dimension = 0u; dimension < problem->head_dim;
               ++dimension)
            output[dimension] *= inverse;
        }
      }
    }
  }
  return AKV_STATUS_OK;
}
