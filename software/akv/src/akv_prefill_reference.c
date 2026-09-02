#include "akv_prefill_internal.h"

#include <math.h>
#include <stdint.h>
#include <string.h>

typedef struct {
  uintptr_t first;
  uintptr_t last;
} contiguous_range_t;

static int finite_positive_f32(float value) {
  uint32_t bits;
  memcpy(&bits, &value, sizeof(bits));
  return (bits >> 31) == 0u && (bits & UINT32_C(0x7fffffff)) != 0u &&
         (bits & UINT32_C(0x7f800000)) != UINT32_C(0x7f800000);
}

static int finite_f16_bits(uint16_t value) {
  return (value & UINT16_C(0x7c00)) != UINT16_C(0x7c00);
}

static int multiply_size(size_t lhs, size_t rhs, size_t *product) {
  return !__builtin_mul_overflow(lhs, rhs, product);
}

static int contiguous_range(const void *base, size_t elements,
                            size_t element_bytes, contiguous_range_t *range) {
  size_t bytes;
  if (base == NULL || elements == 0u || element_bytes == 0u ||
      !multiply_size(elements, element_bytes, &bytes) ||
      __builtin_add_overflow((uintptr_t)base, bytes - 1u, &range->last))
    return 0;
  range->first = (uintptr_t)base;
  return 1;
}

static int ranges_overlap(contiguous_range_t lhs, contiguous_range_t rhs) {
  return lhs.first <= rhs.last && rhs.first <= lhs.last;
}

akv_status_t akv_attention_v2_prefill_validate(
    const akv_device_t *device,
    const akv_attention_v2_prefill_problem_t *problem,
    const akv_attention_v2_prefill_workspace_t *workspace,
    uint32_t *past_tokens, uint32_t *maximum_prefix) {
  if (device == NULL || problem == NULL || workspace == NULL ||
      past_tokens == NULL || maximum_prefix == NULL ||
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

  size_t query_rows;
  size_t query_elements;
  size_t kv_rows;
  size_t kv_elements;
  size_t mask_elements;
  if (!multiply_size(problem->query_heads, problem->query_tokens,
                     &query_rows) ||
      !multiply_size(query_rows, problem->head_dim, &query_elements) ||
      !multiply_size(problem->kv_heads, problem->kv_capacity, &kv_rows) ||
      !multiply_size(kv_rows, problem->head_dim, &kv_elements) ||
      !multiply_size(problem->query_tokens, problem->kv_capacity,
                     &mask_elements))
    return AKV_STATUS_RANGE;

  contiguous_range_t query_range;
  contiguous_range_t key_range;
  contiguous_range_t value_range;
  contiguous_range_t mask_range;
  contiguous_range_t output_range;
  contiguous_range_t workspace_range;
  if (!contiguous_range(problem->query, query_elements, sizeof(float),
                        &query_range) ||
      !contiguous_range(problem->key, kv_elements, sizeof(uint16_t),
                        &key_range) ||
      !contiguous_range(problem->value, kv_elements, sizeof(uint16_t),
                        &value_range) ||
      !contiguous_range(problem->mask, mask_elements, sizeof(uint16_t),
                        &mask_range) ||
      !contiguous_range(problem->output, query_elements, sizeof(float),
                        &output_range) ||
      !contiguous_range(workspace, 1u, sizeof(*workspace), &workspace_range))
    return AKV_STATUS_RANGE;

  const contiguous_range_t read_ranges[] = {
      query_range, key_range, value_range, mask_range};
  const contiguous_range_t write_ranges[] = {output_range, workspace_range};
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
    const uint16_t *const token_mask =
        problem->mask + (size_t)token * problem->kv_capacity;
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
  const akv_status_t validation = akv_attention_v2_prefill_validate(
      device, problem, workspace, &past_tokens, &maximum_prefix);
  if (validation != AKV_STATUS_OK) return validation;
  (void)maximum_prefix;

  const uint32_t q_rows = problem->query_heads / problem->kv_heads;
  for (uint32_t kv_head = 0u; kv_head < problem->kv_heads; ++kv_head) {
    const uint32_t first_qhead = kv_head * q_rows;
    const uint16_t *const key_base =
        problem->key +
        (size_t)kv_head * problem->kv_capacity * problem->head_dim;
    const uint16_t *const value_base =
        problem->value +
        (size_t)kv_head * problem->kv_capacity * problem->head_dim;

    for (uint32_t token_start = 0u; token_start < problem->query_tokens;
         token_start += AKV_PREFILL_QUERY_BLOCK_TOKENS) {
      uint32_t token_count = problem->query_tokens - token_start;
      if (token_count > AKV_PREFILL_QUERY_BLOCK_TOKENS)
        token_count = AKV_PREFILL_QUERY_BLOCK_TOKENS;

      for (uint32_t local_token = 0u; local_token < token_count;
           ++local_token) {
        const uint32_t token = token_start + local_token;
        for (uint32_t head = 0u; head < q_rows; ++head) {
          const float *const query =
              problem->query +
              ((size_t)(first_qhead + head) * problem->query_tokens + token) *
                  problem->head_dim;
          for (uint32_t dimension = 0u; dimension < problem->head_dim;
               ++dimension) {
            workspace->query[local_token][head][dimension] =
                f32_to_f16(query[dimension]);
          }
          workspace->maximum[local_token][head] = -INFINITY;
          workspace->sum[local_token][head] = 0.0f;
          float *const output =
              problem->output +
              ((size_t)token * problem->query_heads + first_qhead + head) *
                  problem->head_dim;
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
          const uint16_t *const mask =
              problem->mask + (size_t)token * problem->kv_capacity +
              tile_start;

          for (uint32_t head = 0u; head < q_rows; ++head) {
            float tile_maximum = -INFINITY;
            for (uint32_t sequence = 0u; sequence < active_tokens;
                 ++sequence) {
              const uint16_t *const key =
                  key_base +
                  (size_t)(tile_start + sequence) * problem->head_dim;
              float dot = 0.0f;
              for (uint32_t dimension = 0u; dimension < problem->head_dim;
                   ++dimension) {
                dot += f16_to_f32(workspace->query[local_token][head][dimension]) *
                       f16_to_f32(key[dimension]);
              }
              const float score = dot * problem->scale + f16_to_f32(mask[sequence]);
              workspace->score[0][head][sequence] = score;
              if (score > tile_maximum) tile_maximum = score;
            }

            const float old_maximum = workspace->maximum[local_token][head];
            const float new_maximum =
                tile_maximum > old_maximum ? tile_maximum : old_maximum;
            const float old_scale =
                isinf(old_maximum) && old_maximum < 0.0f
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

            float *const output =
                problem->output +
                ((size_t)token * problem->query_heads + first_qhead + head) *
                    problem->head_dim;
            for (uint32_t dimension = 0u; dimension < problem->head_dim;
                 ++dimension) {
              float accumulated = output[dimension] * old_scale;
              for (uint32_t sequence = 0u; sequence < active_tokens;
                   ++sequence) {
                const uint16_t *const value =
                    value_base +
                    (size_t)(tile_start + sequence) * problem->head_dim;
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
          float *const output =
              problem->output +
              ((size_t)token * problem->query_heads + first_qhead + head) *
                  problem->head_dim;
          for (uint32_t dimension = 0u; dimension < problem->head_dim;
               ++dimension)
            output[dimension] *= inverse;
        }
      }
    }
  }
  return AKV_STATUS_OK;
}
