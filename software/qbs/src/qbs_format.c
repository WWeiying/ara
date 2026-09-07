#include "qbs/qbs_format.h"

#include <string.h>

qbs_format_family_t qbs_format_family(unsigned profile) {
  switch (profile) {
  case QBS_WEIGHT_PROFILE_Q4_0:
  case QBS_WEIGHT_PROFILE_Q5_0:
  case QBS_WEIGHT_PROFILE_Q8_0_WEIGHT:
    return QBS_FORMAT_GROUPED_INTEGER;
  case QBS_WEIGHT_PROFILE_Q2_K:
  case QBS_WEIGHT_PROFILE_Q3_K:
  case QBS_WEIGHT_PROFILE_Q4_K:
  case QBS_WEIGHT_PROFILE_Q5_K:
  case QBS_WEIGHT_PROFILE_Q6_K:
    return QBS_FORMAT_HIERARCHICAL_INTEGER;
  case QBS_WEIGHT_PROFILE_IQ4_NL:
    return QBS_FORMAT_CODEBOOK;
  default:
    return QBS_FORMAT_INVALID;
  }
}

static int checked_span(const void *base, size_t bytes, uintptr_t *last) {
  return base != NULL && bytes != 0u &&
         !__builtin_add_overflow((uintptr_t)base, bytes - 1u, last);
}

/* Exact conversion, independent of host rounding mode, including subnormals. */
static int exact_f16(float value, uint16_t *half) {
  uint32_t bits;
  memcpy(&bits, &value, sizeof(bits));
  const uint32_t sign = (bits >> 16) & 0x8000u;
  const uint32_t mag = bits & 0x7fffffffu;
  if (mag == 0u) {
    *half = (uint16_t)sign;
    return 1;
  }
  const unsigned exponent = (bits >> 23) & 255u;
  const uint32_t fraction = bits & 0x7fffffu;
  if (exponent < 103u || exponent > 142u) return 0;
  if (exponent >= 113u) {
    if ((fraction & 0x1fffu) != 0u) return 0;
    *half = (uint16_t)(sign | ((exponent - 112u) << 10) |
                       (fraction >> 13));
  } else {
    const unsigned shift = 126u - exponent;
    const uint32_t mantissa = fraction | 0x800000u;
    if ((mantissa & ((UINT32_C(1) << shift) - 1u)) != 0u) return 0;
    *half = (uint16_t)(sign | (mantissa >> shift));
  }
  return 1;
}

static int quant_at(const qbs_grouped_integer_t *s, uint32_t row,
                    uint32_t element) {
  const size_t bit = (size_t)element * s->bits;
  const uint8_t *p = (const uint8_t *)s->quants +
                     (size_t)row * s->row_stride_bytes + bit / 8u;
  unsigned value = p[0];
  if (bit % 8u + s->bits > 8u) value |= (unsigned)p[1] << 8;
  value = (value >> (bit % 8u)) & ((1u << s->bits) - 1u);
  int result = (int)value;
  if (s->signed_quants && (value & (1u << (s->bits - 1u))))
    result -= (int)(1u << s->bits);
  const size_t group = (size_t)row * (s->k_elements / s->group_elements) +
                       element / s->group_elements;
  return result - (s->zero_points ? s->zero_points[group] : 0);
}

qbs_status_t qbs_grouped_integer_size(const qbs_grouped_integer_t *s,
                                     unsigned profile, size_t *bytes) {
  if (s == NULL || bytes == NULL || s->quants == NULL || s->scales == NULL)
    return QBS_STATUS_BAD_ARGUMENT;
  if (qbs_format_family(profile) != QBS_FORMAT_GROUPED_INTEGER)
    return QBS_STATUS_PROFILE;
  if (s->rows == 0u || s->k_elements == 0u || s->bits < 2u ||
      s->bits > 8u || s->signed_quants > 1u || s->group_elements < 32u ||
      s->group_elements > 256u ||
      (s->group_elements & (s->group_elements - 1u)) != 0u ||
      s->k_elements % s->group_elements != 0u)
    return QBS_STATUS_SHAPE;

  size_t row_bits, row_bytes, input_bytes, groups, meta_bytes, output_bytes;
  if (__builtin_mul_overflow((size_t)s->k_elements, (size_t)s->bits, &row_bits) ||
      __builtin_add_overflow(row_bits, (size_t)7, &row_bytes))
    return QBS_STATUS_SIZE_OVERFLOW;
  row_bytes /= 8u;
  if (s->row_stride_bytes < row_bytes) return QBS_STATUS_SHAPE;
  if (__builtin_mul_overflow((size_t)s->rows - 1u, s->row_stride_bytes, &input_bytes) ||
      __builtin_add_overflow(input_bytes, row_bytes, &input_bytes) ||
      __builtin_mul_overflow((size_t)s->rows,
                            s->k_elements / s->group_elements, &groups) ||
      __builtin_mul_overflow(groups, sizeof(float), &meta_bytes))
    return QBS_STATUS_SIZE_OVERFLOW;
  if (s->quant_bytes < input_bytes || s->scale_count < groups ||
      (s->zero_points && s->zero_point_count < groups))
    return QBS_STATUS_BUFFER_TOO_SMALL;
  if ((uintptr_t)s->scales % _Alignof(float) ||
      (s->zero_points && (uintptr_t)s->zero_points % _Alignof(int16_t)))
    return QBS_STATUS_BUFFER_ALIGNMENT;
  uintptr_t last;
  if (!checked_span(s->quants, input_bytes, &last) ||
      !checked_span(s->scales, meta_bytes, &last) ||
      (s->zero_points && !checked_span(s->zero_points,
                                       groups * sizeof(int16_t), &last)))
    return QBS_STATUS_SIZE_OVERFLOW;
  output_bytes = qbs_weight_storage_bytes(profile, QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                                           s->rows, s->k_elements / 32u);
  if (output_bytes == 0u) return QBS_STATUS_SIZE_OVERFLOW;
  for (size_t group = 0; group < groups; ++group) {
    uint16_t half;
    if (!exact_f16(s->scales[group], &half))
      return QBS_STATUS_NUMERICAL_CONTRACT;
  }
  const int limit = profile == QBS_WEIGHT_PROFILE_Q4_0 ? 8 :
                    profile == QBS_WEIGHT_PROFILE_Q5_0 ? 16 : 128;
  for (uint32_t row = 0; row < s->rows; ++row)
    for (uint32_t element = 0; element < s->k_elements; ++element) {
      const int value = quant_at(s, row, element);
      if (value < -limit || value >= limit)
        return QBS_STATUS_NUMERICAL_CONTRACT;
    }
  *bytes = output_bytes;
  return QBS_STATUS_OK;
}

static int overlaps(const void *a, size_t an, const void *b, size_t bn) {
  uintptr_t alast, blast;
  if (!checked_span(a, an, &alast) || !checked_span(b, bn, &blast)) return 1;
  return (uintptr_t)a <= blast && (uintptr_t)b <= alast;
}

qbs_status_t qbs_import_grouped_integer(const qbs_grouped_integer_t *s,
                                       unsigned profile, void *dst,
                                       size_t capacity) {
  if (s == NULL) return QBS_STATUS_BAD_ARGUMENT;
  const qbs_grouped_integer_t snapshot = *s;
  s = &snapshot;
  size_t bytes;
  const qbs_status_t status = qbs_grouped_integer_size(s, profile, &bytes);
  if (status != QBS_STATUS_OK) return status;
  if (dst == NULL) return QBS_STATUS_BAD_ARGUMENT;
  if (capacity < bytes) return QBS_STATUS_BUFFER_TOO_SMALL;
  uintptr_t last;
  if (!checked_span(dst, bytes, &last)) return QBS_STATUS_SIZE_OVERFLOW;
  const size_t groups = (size_t)s->rows * (s->k_elements / s->group_elements);
  if (overlaps(dst, bytes, s->quants, s->quant_bytes) ||
      overlaps(dst, bytes, s->scales, groups * sizeof(float)) ||
      (s->zero_points && overlaps(dst, bytes, s->zero_points,
                                   groups * sizeof(int16_t))))
    return QBS_STATUS_BAD_ARGUMENT;

  const size_t block_bytes = qbs_weight_block_bytes(profile);
  for (uint32_t row = 0; row < s->rows; ++row) {
    for (uint32_t block = 0; block < s->k_elements / 32u; ++block) {
      uint8_t *p = (uint8_t *)dst +
                   ((size_t)row * (s->k_elements / 32u) + block) * block_bytes;
      const size_t group = (size_t)row * (s->k_elements / s->group_elements) +
                           block * 32u / s->group_elements;
      uint16_t half = 0;
      (void)exact_f16(s->scales[group], &half);
      memset(p, 0, block_bytes);
      p[0] = (uint8_t)half;
      p[1] = (uint8_t)(half >> 8);
      for (unsigned i = 0; i < 32u; ++i) {
        const int q = quant_at(s, row, block * 32u + i);
        if (profile == QBS_WEIGHT_PROFILE_Q8_0_WEIGHT) {
          p[2u + i] = (uint8_t)q;
        } else {
          const unsigned u = (unsigned)(q +
              (profile == QBS_WEIGHT_PROFILE_Q4_0 ? 8 : 16));
          const size_t offset = profile == QBS_WEIGHT_PROFILE_Q4_0 ? 2u : 6u;
          p[offset + i % 16u] |= (uint8_t)((u & 15u) << (i < 16u ? 0u : 4u));
          if (profile == QBS_WEIGHT_PROFILE_Q5_0)
            p[2u + i / 8u] |= (uint8_t)((u >> 4) << (i % 8u));
        }
      }
    }
  }
  return QBS_STATUS_OK;
}
