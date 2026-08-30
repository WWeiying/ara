#include "qbs_ref.h"

#include <fenv.h>
#include <limits.h>
#include <math.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

_Static_assert(sizeof(qbs_block_q4_k_t) == QBS_Q4_K_BLOCK_BYTES,
               "invalid Q4_K block size");
_Static_assert(offsetof(qbs_block_q4_k_t, d) == 0, "invalid Q4_K d offset");
_Static_assert(offsetof(qbs_block_q4_k_t, dmin) == 2,
               "invalid Q4_K dmin offset");
_Static_assert(offsetof(qbs_block_q4_k_t, scales) == 4,
               "invalid Q4_K scales offset");
_Static_assert(offsetof(qbs_block_q4_k_t, qs) == 16,
               "invalid Q4_K payload offset");

_Static_assert(sizeof(qbs_block_q5_k_t) == QBS_Q5_K_BLOCK_BYTES,
               "invalid Q5_K block size");
_Static_assert(offsetof(qbs_block_q5_k_t, d) == 0, "invalid Q5_K d offset");
_Static_assert(offsetof(qbs_block_q5_k_t, dmin) == 2,
               "invalid Q5_K dmin offset");
_Static_assert(offsetof(qbs_block_q5_k_t, scales) == 4,
               "invalid Q5_K scales offset");
_Static_assert(offsetof(qbs_block_q5_k_t, qh) == 16,
               "invalid Q5_K high-plane offset");
_Static_assert(offsetof(qbs_block_q5_k_t, qs) == 48,
               "invalid Q5_K low-plane offset");

_Static_assert(sizeof(qbs_block_q6_k_t) == QBS_Q6_K_BLOCK_BYTES,
               "invalid Q6_K block size");
_Static_assert(offsetof(qbs_block_q6_k_t, ql) == 0,
               "invalid Q6_K low-plane offset");
_Static_assert(offsetof(qbs_block_q6_k_t, qh) == 128,
               "invalid Q6_K high-plane offset");
_Static_assert(offsetof(qbs_block_q6_k_t, scales) == 192,
               "invalid Q6_K scales offset");
_Static_assert(offsetof(qbs_block_q6_k_t, d) == 208,
               "invalid Q6_K d offset");

_Static_assert(sizeof(qbs_block_q3_k_t) == QBS_Q3_K_BLOCK_BYTES,
               "invalid Q3_K block size");
_Static_assert(offsetof(qbs_block_q3_k_t, hmask) == 0,
               "invalid Q3_K high-mask offset");
_Static_assert(offsetof(qbs_block_q3_k_t, qs) == 32,
               "invalid Q3_K low-plane offset");
_Static_assert(offsetof(qbs_block_q3_k_t, scales) == 96,
               "invalid Q3_K scales offset");
_Static_assert(offsetof(qbs_block_q3_k_t, d) == 108,
               "invalid Q3_K d offset");

_Static_assert(sizeof(qbs_block_q4_0_t) == QBS_Q4_0_BLOCK_BYTES,
               "invalid Q4_0 block size");
_Static_assert(offsetof(qbs_block_q4_0_t, d) == 0,
               "invalid Q4_0 d offset");
_Static_assert(offsetof(qbs_block_q4_0_t, qs) == 2,
               "invalid Q4_0 payload offset");

_Static_assert(sizeof(qbs_block_q2_k_t) == QBS_Q2_K_BLOCK_BYTES,
               "invalid Q2_K block size");
_Static_assert(offsetof(qbs_block_q2_k_t, scales) == 0,
               "invalid Q2_K scales offset");
_Static_assert(offsetof(qbs_block_q2_k_t, qs) == 16,
               "invalid Q2_K payload offset");
_Static_assert(offsetof(qbs_block_q2_k_t, d) == 80,
               "invalid Q2_K d offset");
_Static_assert(offsetof(qbs_block_q2_k_t, dmin) == 82,
               "invalid Q2_K dmin offset");

_Static_assert(sizeof(qbs_block_q5_0_t) == QBS_Q5_0_BLOCK_BYTES,
               "invalid Q5_0 block size");
_Static_assert(offsetof(qbs_block_q5_0_t, d) == 0,
               "invalid Q5_0 d offset");
_Static_assert(offsetof(qbs_block_q5_0_t, qh) == 2,
               "invalid Q5_0 high-plane offset");
_Static_assert(offsetof(qbs_block_q5_0_t, qs) == 6,
               "invalid Q5_0 low-plane offset");

_Static_assert(sizeof(qbs_block_iq4_nl_t) == QBS_IQ4_NL_BLOCK_BYTES,
               "invalid IQ4_NL block size");
_Static_assert(offsetof(qbs_block_iq4_nl_t, d) == 0,
               "invalid IQ4_NL d offset");
_Static_assert(offsetof(qbs_block_iq4_nl_t, qs) == 2,
               "invalid IQ4_NL payload offset");

_Static_assert(sizeof(qbs_block_q8_k_t) == QBS_Q8_K_BLOCK_BYTES,
               "invalid Q8_K block size");
_Static_assert(offsetof(qbs_block_q8_k_t, d) == 0, "invalid Q8_K d offset");
_Static_assert(offsetof(qbs_block_q8_k_t, qs) == 4,
               "invalid Q8_K payload offset");
_Static_assert(offsetof(qbs_block_q8_k_t, bsums) == 260,
               "invalid Q8_K bsums offset");
_Static_assert(sizeof(qbs_block_q8_kx4_t) == 4 * QBS_Q8_K_BLOCK_BYTES,
               "invalid Q8_Kx4 block size");

_Static_assert(sizeof(qbs_block_q8_0_t) == QBS_Q8_0_BLOCK_BYTES,
               "invalid Q8_0 block size");
_Static_assert(sizeof(qbs_block_q8_0_t) == QBS_Q8_0_WEIGHT_BLOCK_BYTES,
               "invalid Q8_0 weight block size");
_Static_assert(offsetof(qbs_block_q8_0_t, d) == 0,
               "invalid Q8_0 d offset");
_Static_assert(offsetof(qbs_block_q8_0_t, qs) == 2,
               "invalid Q8_0 payload offset");
_Static_assert(sizeof(qbs_block_q8_0x4_t) == 4 * QBS_Q8_0_BLOCK_BYTES,
               "invalid Q8_0x4 block size");

enum {
  QBS_FFLAG_NX = 1u << 0,
  QBS_FFLAG_UF = 1u << 1,
  QBS_FFLAG_OF = 1u << 2,
  QBS_FFLAG_DZ = 1u << 3,
  QBS_FFLAG_NV = 1u << 4,
};

static bool size_mul(size_t lhs, size_t rhs, size_t *result) {
  if (lhs != 0 && rhs > SIZE_MAX / lhs) return false;
  *result = lhs * rhs;
  return true;
}

static bool address_range_valid(uint64_t base, size_t bytes) {
  if (bytes == 0) return false;
  return (uint64_t)(bytes - 1u) <= UINT64_MAX - base;
}

static size_t weight_block_bytes(unsigned profile) {
  return qbs_weight_block_bytes(profile);
}

static unsigned destination_register_count(unsigned m) {
  if (m == 1) return 1;
  if (m == 2) return 2;
  return 4;
}

static uint32_t host_fp_flags(void) {
  const int flags = fetestexcept(FE_ALL_EXCEPT);
  uint32_t result = 0;
  if (flags & FE_INEXACT) result |= QBS_FFLAG_NX;
  if (flags & FE_UNDERFLOW) result |= QBS_FFLAG_UF;
  if (flags & FE_OVERFLOW) result |= QBS_FFLAG_OF;
  if (flags & FE_DIVBYZERO) result |= QBS_FFLAG_DZ;
  if (flags & FE_INVALID) result |= QBS_FFLAG_NV;
  return result;
}

static float rounded_mul(float lhs, float rhs) {
  volatile float result = lhs * rhs;
  return result;
}

static float rounded_div(float lhs, float rhs) {
  volatile float result = lhs / rhs;
  return result;
}

static float rounded_i32_to_f32(int32_t value) {
  volatile float result = (float)value;
  return result;
}

static bool i64_to_i32(int64_t value, int32_t *result) {
  if (value < INT32_MIN || value > INT32_MAX) return false;
  *result = (int32_t)value;
  return true;
}

static int nearest_int(float value) {
  volatile float biased = value + 12582912.0f;
  uint32_t bits;
  memcpy(&bits, (const void *)&biased, sizeof(bits));
  return (int)(bits & UINT32_C(0x007fffff)) - 0x00400000;
}

const char *qbs_ref_status_string(qbs_ref_status_t status) {
  switch (status) {
    case QBS_REF_OK:
      return "ok";
    case QBS_REF_BAD_ARGUMENT:
      return "bad_argument";
    case QBS_REF_DESCRIPTOR_ALIGNMENT:
      return "descriptor_alignment";
    case QBS_REF_DESCRIPTOR_VERSION:
      return "descriptor_version";
    case QBS_REF_DESCRIPTOR_RESERVED:
      return "descriptor_reserved";
    case QBS_REF_WEIGHT_PROFILE:
      return "weight_profile";
    case QBS_REF_ACTIVATION_PROFILE:
      return "activation_profile";
    case QBS_REF_WEIGHT_LAYOUT:
      return "weight_layout";
    case QBS_REF_ACTIVATION_LAYOUT:
      return "activation_layout";
    case QBS_REF_M_RANGE:
      return "m_range";
    case QBS_REF_N_RANGE:
      return "n_range";
    case QBS_REF_K_RANGE:
      return "k_range";
    case QBS_REF_VLEN:
      return "vlen";
    case QBS_REF_VD_ALIGNMENT:
      return "vd_alignment";
    case QBS_REF_BASE_ALIGNMENT:
      return "base_alignment";
    case QBS_REF_ADDRESS_OVERFLOW:
      return "address_overflow";
    case QBS_REF_CONTEXT_ENCODING:
      return "context_encoding";
    case QBS_REF_CONTEXT_UNSUPPORTED:
      return "context_unsupported";
    case QBS_REF_CONTEXT_INVALID:
      return "context_invalid";
    case QBS_REF_CONTEXT_GENERATION:
      return "context_generation";
    case QBS_REF_CONTEXT_METADATA:
      return "context_metadata";
    case QBS_REF_BUFFER_SIZE:
      return "buffer_size";
    case QBS_REF_OUTPUT_SIZE:
      return "output_size";
    case QBS_REF_INTEGER_OVERFLOW:
      return "integer_overflow";
    case QBS_REF_ALLOCATION_FAILURE:
      return "allocation_failure";
  }
  return "unknown";
}

float qbs_ref_fp16_to_fp32(qbs_fp16_t value) {
  const uint32_t sign = (uint32_t)(value & 0x8000u) << 16;
  uint32_t exponent = (value >> 10) & 0x1fu;
  uint32_t fraction = value & 0x03ffu;
  uint32_t bits;

  if (exponent == 0) {
    if (fraction == 0) {
      bits = sign;
    } else {
      int shift = 0;
      while ((fraction & 0x0400u) == 0) {
        fraction <<= 1;
        ++shift;
      }
      fraction &= 0x03ffu;
      exponent = (uint32_t)(113 - shift);
      bits = sign | (exponent << 23) | (fraction << 13);
    }
  } else if (exponent == 0x1fu) {
    bits = sign | 0x7f800000u | (fraction << 13);
    if (fraction != 0) bits |= 0x00400000u;
  } else {
    exponent += 112u;
    bits = sign | (exponent << 23) | (fraction << 13);
  }

  float result;
  memcpy(&result, &bits, sizeof(result));
  return result;
}

uint64_t qbs_ref_capability_word(unsigned index, unsigned vlen_bits) {
  return qbs_capability_word(index, vlen_bits);
}

size_t qbs_ref_weight_storage_bytes(unsigned weight_profile,
                                    unsigned weight_layout, unsigned n,
                                    unsigned k_blocks) {
  const size_t block_bytes = weight_block_bytes(weight_profile);
  if (block_bytes == 0 || n == 0 || k_blocks == 0) return 0;
  size_t rows = n;
  if (weight_layout == QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR) {
    rows = (n + 3u) & ~3u;
  } else if (weight_layout != QBS_WEIGHT_LAYOUT_ROW_MAJOR) {
    return 0;
  }
  size_t blocks;
  size_t bytes;
  if (!size_mul(rows, k_blocks, &blocks) ||
      !size_mul(blocks, block_bytes, &bytes)) {
    return 0;
  }
  return bytes;
}

size_t qbs_ref_activation_storage_bytes_for_profile(
    unsigned activation_profile, unsigned activation_layout, unsigned m,
    unsigned k_blocks) {
  if (m == 0 || k_blocks == 0) return 0;
  const size_t block_bytes =
      qbs_activation_block_bytes(activation_profile);
  if (block_bytes == 0) return 0;
  size_t blocks;
  size_t bytes;
  if (activation_layout == QBS_ACTIVATION_LAYOUT_ROW_MAJOR) {
    if (!size_mul(m, k_blocks, &blocks) ||
        !size_mul(blocks, block_bytes, &bytes)) {
      return 0;
    }
    return bytes;
  }
  if (activation_layout == QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED && m == 4) {
    if (!size_mul(k_blocks, 4u * block_bytes, &bytes)) return 0;
    return bytes;
  }
  return 0;
}

size_t qbs_ref_activation_storage_bytes(unsigned activation_layout,
                                        unsigned m, unsigned k_blocks) {
  return qbs_ref_activation_storage_bytes_for_profile(
      QBS_ACTIVATION_PROFILE_Q8_K, activation_layout, m, k_blocks);
}

qbs_ref_status_t qbs_ref_validate_descriptor(
    const qbs_descriptor_t *descriptor, unsigned m, unsigned vd,
    unsigned vlen_bits, uint64_t activation_base) {
  if (descriptor == NULL) return QBS_REF_BAD_ARGUMENT;
  if (((uintptr_t)descriptor &
       (((uintptr_t)1u << QBS_DESCRIPTOR_ALIGNMENT_LOG2) - 1u)) !=
      0) {
    return QBS_REF_DESCRIPTOR_ALIGNMENT;
  }
  if (vlen_bits < 32 || (vlen_bits % 32u) != 0) return QBS_REF_VLEN;
  if (m == 0 || m > QBS_MAX_M) return QBS_REF_M_RANGE;

  const qbs_descriptor_fields_t fields =
      qbs_unpack_descriptor_header(descriptor->header);
  if (fields.descriptor_version != QBS_DESCRIPTOR_VERSION)
    return QBS_REF_DESCRIPTOR_VERSION;
  if ((descriptor->header >> 47) != 0) return QBS_REF_DESCRIPTOR_RESERVED;
  if (qbs_weight_block_bytes(fields.weight_profile) == 0)
    return QBS_REF_WEIGHT_PROFILE;
  if (qbs_activation_block_bytes(fields.activation_profile) == 0 ||
      !qbs_profiles_compatible(fields.weight_profile,
                               fields.activation_profile))
    return QBS_REF_ACTIVATION_PROFILE;
  if (fields.weight_layout != QBS_WEIGHT_LAYOUT_ROW_MAJOR &&
      fields.weight_layout != QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR)
    return QBS_REF_WEIGHT_LAYOUT;
  if (fields.activation_layout != QBS_ACTIVATION_LAYOUT_ROW_MAJOR &&
      fields.activation_layout != QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED)
    return QBS_REF_ACTIVATION_LAYOUT;
  if (fields.activation_layout == QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED &&
      m != 4)
    return QBS_REF_ACTIVATION_LAYOUT;

  const unsigned max_n =
      vlen_bits / 32u < QBS_MAX_N ? vlen_bits / 32u : QBS_MAX_N;
  if (fields.n == 0 || fields.n > max_n) return QBS_REF_N_RANGE;
  if (fields.k_blocks == 0 || fields.k_blocks > QBS_MAX_K_BLOCKS)
    return QBS_REF_K_RANGE;
  if (fields.activation_access == QBS_ACTIVATION_ACCESS_DIRECT &&
      (fields.context_id != 0 || fields.context_generation != 0))
    return QBS_REF_CONTEXT_ENCODING;
  if (fields.activation_access != QBS_ACTIVATION_ACCESS_DIRECT &&
      (fields.context_id >= QBS_ACTIVATION_CONTEXT_COUNT ||
       fields.activation_profile != QBS_ACTIVATION_PROFILE_Q8_K ||
       fields.activation_layout != QBS_ACTIVATION_LAYOUT_ROW_MAJOR ||
       m > QBS_ACTIVATION_CONTEXT_MAX_M ||
       fields.k_blocks > QBS_ACTIVATION_CONTEXT_MAX_K_BLOCKS))
    return QBS_REF_CONTEXT_UNSUPPORTED;

  const unsigned registers = destination_register_count(m);
  if ((vd % registers) != 0 || vd + registers > 32u)
    return QBS_REF_VD_ALIGNMENT;
  if ((descriptor->weight_base &
       ((UINT64_C(1) << QBS_WEIGHT_BASE_ALIGNMENT_LOG2) - 1u)) != 0)
    return QBS_REF_BASE_ALIGNMENT;
  if ((fields.activation_access == QBS_ACTIVATION_ACCESS_DIRECT ||
       fields.activation_access == QBS_ACTIVATION_ACCESS_FILL) &&
      (activation_base &
       ((UINT64_C(1) << QBS_ACTIVATION_BASE_ALIGNMENT_LOG2) - 1u)) != 0)
    return QBS_REF_BASE_ALIGNMENT;

  const size_t weight_bytes = qbs_ref_weight_storage_bytes(
      fields.weight_profile, fields.weight_layout, fields.n, fields.k_blocks);
  const size_t activation_bytes =
      qbs_ref_activation_storage_bytes_for_profile(
          fields.activation_profile, fields.activation_layout, m,
          fields.k_blocks);
  if (weight_bytes == 0 || activation_bytes == 0)
    return QBS_REF_ADDRESS_OVERFLOW;
  if (!address_range_valid(descriptor->weight_base, weight_bytes))
    return QBS_REF_ADDRESS_OVERFLOW;
  if ((fields.activation_access == QBS_ACTIVATION_ACCESS_DIRECT ||
       fields.activation_access == QBS_ACTIVATION_ACCESS_FILL) &&
      !address_range_valid(activation_base, activation_bytes))
    return QBS_REF_ADDRESS_OVERFLOW;
  return QBS_REF_OK;
}

qbs_ref_status_t qbs_ref_repack_weight_r4(
    unsigned weight_profile, const void *row_major, size_t row_major_bytes,
    unsigned n, unsigned k_blocks, void *r4, size_t r4_bytes) {
  if (row_major == NULL || r4 == NULL || n == 0 || k_blocks == 0)
    return QBS_REF_BAD_ARGUMENT;
  const size_t block_bytes = weight_block_bytes(weight_profile);
  const size_t source_bytes = qbs_ref_weight_storage_bytes(
      weight_profile, QBS_WEIGHT_LAYOUT_ROW_MAJOR, n, k_blocks);
  const size_t destination_bytes = qbs_ref_weight_storage_bytes(
      weight_profile, QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR, n, k_blocks);
  if (block_bytes == 0) return QBS_REF_WEIGHT_PROFILE;
  if (row_major_bytes < source_bytes || r4_bytes < destination_bytes)
    return QBS_REF_BUFFER_SIZE;
  memset(r4, 0, destination_bytes);
  for (unsigned row = 0; row < n; ++row) {
    for (unsigned block = 0; block < k_blocks; ++block) {
      const size_t source_index = (size_t)row * k_blocks + block;
      const size_t destination_index =
          ((size_t)(row / 4u) * k_blocks + block) * 4u + row % 4u;
      memcpy((uint8_t *)r4 + destination_index * block_bytes,
             (const uint8_t *)row_major + source_index * block_bytes,
             block_bytes);
    }
  }
  return QBS_REF_OK;
}

qbs_ref_status_t qbs_ref_pack_activation_m4_profile(
    unsigned activation_profile, const void *row_major,
    size_t row_major_bytes, unsigned k_blocks, void *interleaved,
    size_t interleaved_bytes) {
  if (row_major == NULL || interleaved == NULL || k_blocks == 0)
    return QBS_REF_BAD_ARGUMENT;

  const size_t block_bytes =
      qbs_activation_block_bytes(activation_profile);
  const size_t scale_bytes =
      qbs_activation_scale_bytes(activation_profile);
  const size_t quant_bytes =
      qbs_activation_quant_bytes(activation_profile);
  const size_t aux_count = qbs_activation_aux_count(activation_profile);
  const size_t aux_element_bytes =
      qbs_activation_aux_element_bytes(activation_profile);
  size_t row_major_required;
  size_t interleaved_required;
  if (block_bytes == 0 || scale_bytes == 0 || quant_bytes == 0 ||
      !size_mul(4u * k_blocks, block_bytes, &row_major_required) ||
      !size_mul(k_blocks, 4u * block_bytes, &interleaved_required))
    return QBS_REF_ACTIVATION_PROFILE;
  if (row_major_bytes < row_major_required ||
      interleaved_bytes < interleaved_required)
    return QBS_REF_BUFFER_SIZE;

  for (unsigned block = 0; block < k_blocks; ++block) {
    uint8_t *destination =
        (uint8_t *)interleaved + (size_t)block * 4u * block_bytes;
    for (unsigned context = 0; context < 4; ++context) {
      const uint8_t *source = (const uint8_t *)row_major +
          ((size_t)context * k_blocks + block) * block_bytes;
      memcpy(destination + context * scale_bytes, source, scale_bytes);
      for (unsigned byte = 0; byte < quant_bytes; ++byte) {
        destination[4u * scale_bytes + byte * 4u + context] =
            source[scale_bytes + byte];
      }
      for (unsigned item = 0; item < aux_count; ++item) {
        const size_t source_offset =
            scale_bytes + quant_bytes + item * aux_element_bytes;
        const size_t destination_offset = 4u * scale_bytes +
            4u * quant_bytes +
            ((size_t)item * 4u + context) * aux_element_bytes;
        memcpy(destination + destination_offset, source + source_offset,
               aux_element_bytes);
      }
    }
  }
  return QBS_REF_OK;
}

qbs_ref_status_t qbs_ref_pack_activation_m4(
    const qbs_block_q8_k_t *row_major, size_t row_major_blocks,
    unsigned k_blocks, qbs_block_q8_kx4_t *interleaved,
    size_t interleaved_blocks) {
  return qbs_ref_pack_activation_m4_profile(
      QBS_ACTIVATION_PROFILE_Q8_K, row_major,
      row_major_blocks * sizeof(*row_major), k_blocks, interleaved,
      interleaved_blocks * sizeof(*interleaved));
}

qbs_ref_status_t qbs_ref_quantize_q8_k(const float *input,
                                       size_t input_elements,
                                       qbs_block_q8_k_t *output,
                                       size_t output_blocks) {
  if (input == NULL || output == NULL ||
      input_elements % QBS_BLOCK_ELEMENTS != 0)
    return QBS_REF_BAD_ARGUMENT;
  const size_t blocks = input_elements / QBS_BLOCK_ELEMENTS;
  if (output_blocks < blocks) return QBS_REF_BUFFER_SIZE;

  const int old_round = fegetround();
  if (fesetround(FE_TONEAREST) != 0) return QBS_REF_BAD_ARGUMENT;
  for (size_t block = 0; block < blocks; ++block) {
    const float *source = input + block * QBS_BLOCK_ELEMENTS;
    qbs_block_q8_k_t *destination = &output[block];
    float maximum = 0.0f;
    float absolute_maximum = 0.0f;
    for (unsigned element = 0; element < QBS_BLOCK_ELEMENTS; ++element) {
      const float absolute = fabsf(source[element]);
      if (absolute > absolute_maximum) {
        absolute_maximum = absolute;
        maximum = source[element];
      }
    }
    if (absolute_maximum == 0.0f) {
      memset(destination, 0, sizeof(*destination));
      continue;
    }
    const float scale = rounded_div(-127.0f, maximum);
    destination->d = rounded_div(1.0f, scale);
    for (unsigned subgroup = 0; subgroup < 16; ++subgroup) {
      int sum = 0;
      for (unsigned item = 0; item < 16; ++item) {
        const unsigned element = subgroup * 16u + item;
        int quantized = nearest_int(rounded_mul(source[element], scale));
        if (quantized > 127) quantized = 127;
        destination->qs[element] = (int8_t)quantized;
        sum += quantized;
      }
      destination->bsums[subgroup] = (int16_t)sum;
    }
  }
  if (old_round != -1) (void)fesetround(old_round);
  return QBS_REF_OK;
}

void qbs_ref_decode_q4_k(const qbs_block_q4_k_t *block, int8_t values[256],
                         uint8_t scales[8], uint8_t mins[8]) {
  for (unsigned group = 0; group < 8; ++group) {
    if (group < 4) {
      scales[group] = block->scales[group] & 0x3fu;
      mins[group] = block->scales[group + 4u] & 0x3fu;
    } else {
      scales[group] = (block->scales[group + 4u] & 0x0fu) |
                      ((block->scales[group - 4u] >> 6) << 4);
      mins[group] = (block->scales[group + 4u] >> 4) |
                    ((block->scales[group] >> 6) << 4);
    }
  }
  for (unsigned element = 0; element < QBS_BLOCK_ELEMENTS; ++element) {
    const unsigned packet = element / 64u;
    const unsigned within = element % 64u;
    const uint8_t packed = block->qs[packet * 32u + within % 32u];
    values[element] =
        (int8_t)(within < 32u ? packed & 0x0fu : packed >> 4);
  }
}

void qbs_ref_decode_q5_k(const qbs_block_q5_k_t *block, int8_t values[256],
                         uint8_t scales[8], uint8_t mins[8]) {
  for (unsigned group = 0; group < 8; ++group) {
    if (group < 4) {
      scales[group] = block->scales[group] & 0x3fu;
      mins[group] = block->scales[group + 4u] & 0x3fu;
    } else {
      scales[group] = (block->scales[group + 4u] & 0x0fu) |
                      ((block->scales[group - 4u] >> 6) << 4);
      mins[group] = (block->scales[group + 4u] >> 4) |
                    ((block->scales[group] >> 6) << 4);
    }
  }
  for (unsigned element = 0; element < QBS_Q5_K_BLOCK_ELEMENTS; ++element) {
    const unsigned packet = element / 64u;
    const unsigned within = element % 64u;
    const uint8_t packed = block->qs[packet * 32u + within % 32u];
    const unsigned low = within < 32u ? packed & 0x0fu : packed >> 4;
    const unsigned high_bit = packet * 2u + (within >= 32u ? 1u : 0u);
    const unsigned high = (block->qh[within % 32u] >> high_bit) & 1u;
    values[element] = (int8_t)(low | (high << 4));
  }
}

void qbs_ref_decode_q6_k(const qbs_block_q6_k_t *block, int8_t values[256],
                         int8_t scales[16]) {
  memcpy(scales, block->scales, 16);
  for (unsigned element = 0; element < QBS_BLOCK_ELEMENTS; ++element) {
    const unsigned half = element / 128u;
    const unsigned quarter = (element % 128u) / 32u;
    const unsigned lane = element % 32u;
    const unsigned ql_index =
        half * 64u + ((quarter & 1u) != 0 ? 32u : 0u) + lane;
    const unsigned qh_index = half * 32u + lane;
    const unsigned ql_shift = quarter >= 2u ? 4u : 0u;
    const unsigned qh_shift = quarter * 2u;
    const unsigned low = (block->ql[ql_index] >> ql_shift) & 0x0fu;
    const unsigned high = (block->qh[qh_index] >> qh_shift) & 0x03u;
    values[element] = (int8_t)((low | (high << 4)) - 32);
  }
}

void qbs_ref_decode_q3_k(const qbs_block_q3_k_t *block, int8_t values[256],
                         int8_t scales[16]) {
  for (unsigned group = 0; group < 16; ++group) {
    const unsigned within = group & 3u;
    const unsigned region = group >> 2;
    const uint8_t low_meta =
        block->scales[(region & 1u) * 4u + within];
    const uint8_t high_meta = block->scales[8u + within];
    const unsigned low =
        (low_meta >> (region >= 2u ? 4u : 0u)) & 0x0fu;
    const unsigned high = (high_meta >> (2u * region)) & 0x03u;
    scales[group] = (int8_t)((low | (high << 4)) - 32);
  }
  for (unsigned element = 0; element < QBS_Q3_K_BLOCK_ELEMENTS; ++element) {
    const unsigned packet = element / 32u;
    const unsigned lane = element % 32u;
    const uint8_t packed = block->qs[(packet / 4u) * 32u + lane];
    const unsigned low = (packed >> (2u * (packet & 3u))) & 0x03u;
    const bool high = ((block->hmask[lane] >> packet) & 1u) != 0;
    values[element] = (int8_t)low - (high ? 0 : 4);
  }
}

void qbs_ref_decode_q4_0(const qbs_block_q4_0_t *block, int8_t values[32]) {
  for (unsigned element = 0; element < QBS_Q4_0_BLOCK_ELEMENTS; ++element) {
    const uint8_t packed = block->qs[element % 16u];
    const unsigned quant = element < 16u ? packed & 0x0fu : packed >> 4;
    values[element] = (int8_t)quant - 8;
  }
}

void qbs_ref_decode_q8_0(const qbs_block_q8_0_t *block, int8_t values[32]) {
  memcpy(values, block->qs, sizeof(block->qs));
}

void qbs_ref_decode_q2_k(const qbs_block_q2_k_t *block, int8_t values[256],
                         uint8_t scales[16], uint8_t mins[16]) {
  for (unsigned group = 0; group < 16; ++group) {
    scales[group] = block->scales[group] & 0x0fu;
    mins[group] = block->scales[group] >> 4;
  }
  for (unsigned element = 0; element < QBS_Q2_K_BLOCK_ELEMENTS; ++element) {
    const unsigned half = element / 128u;
    const unsigned subgroup = (element % 128u) / 16u;
    const unsigned lane = element % 16u;
    const unsigned byte = half * 32u + (subgroup & 1u) * 16u + lane;
    const unsigned shift = 2u * (subgroup / 2u);
    values[element] = (int8_t)((block->qs[byte] >> shift) & 0x03u);
  }
}

void qbs_ref_decode_q5_0(const qbs_block_q5_0_t *block, int8_t values[32]) {
  for (unsigned element = 0; element < QBS_Q5_0_BLOCK_ELEMENTS; ++element) {
    const uint8_t packed = block->qs[element % 16u];
    const unsigned low = element < 16u ? packed & 0x0fu : packed >> 4;
    const unsigned high = (block->qh[element / 8u] >> (element % 8u)) & 1u;
    values[element] = (int8_t)(low | (high << 4)) - 16;
  }
}

void qbs_ref_decode_iq4_nl(const qbs_block_iq4_nl_t *block,
                           int8_t values[32]) {
  static const int8_t table[16] = {
      -127, -104, -83, -65, -49, -35, -22, -10,
         1,   13,  25,  38,  53,  69,  89, 113,
  };
  for (unsigned element = 0; element < QBS_IQ4_NL_BLOCK_ELEMENTS; ++element) {
    const uint8_t packed = block->qs[element % 16u];
    const unsigned index = element < 16u ? packed & 0x0fu : packed >> 4;
    values[element] = table[index];
  }
}

static void read_activation_block(unsigned profile, unsigned layout,
                                  const void *data, unsigned context,
                                  unsigned block, unsigned k_blocks,
                                  uint8_t destination[QBS_MAX_ACTIVATION_BLOCK_BYTES]) {
  const size_t block_bytes = qbs_activation_block_bytes(profile);
  const size_t scale_bytes = qbs_activation_scale_bytes(profile);
  const size_t quant_bytes = qbs_activation_quant_bytes(profile);
  const size_t aux_count = qbs_activation_aux_count(profile);
  const size_t aux_element_bytes =
      qbs_activation_aux_element_bytes(profile);
  if (layout == QBS_ACTIVATION_LAYOUT_ROW_MAJOR) {
    const size_t index = (size_t)context * k_blocks + block;
    memcpy(destination, (const uint8_t *)data + index * block_bytes,
           block_bytes);
    return;
  }
  const uint8_t *source =
      (const uint8_t *)data + (size_t)block * 4u * block_bytes;
  memcpy(destination, source + context * scale_bytes, scale_bytes);
  for (unsigned byte = 0; byte < quant_bytes; ++byte) {
    destination[scale_bytes + byte] =
        source[4u * scale_bytes + byte * 4u + context];
  }
  for (unsigned item = 0; item < aux_count; ++item) {
    const size_t source_offset = 4u * scale_bytes + 4u * quant_bytes +
        ((size_t)item * 4u + context) * aux_element_bytes;
    const size_t destination_offset =
        scale_bytes + quant_bytes + item * aux_element_bytes;
    memcpy(destination + destination_offset, source + source_offset,
           aux_element_bytes);
  }
}

static const uint8_t *weight_block_address(const void *data, unsigned layout,
                                           unsigned row, unsigned block,
                                           unsigned k_blocks,
                                           size_t block_bytes) {
  size_t index;
  if (layout == QBS_WEIGHT_LAYOUT_ROW_MAJOR) {
    index = (size_t)row * k_blocks + block;
  } else {
    index = ((size_t)(row / 4u) * k_blocks + block) * 4u + row % 4u;
  }
  return (const uint8_t *)data + index * block_bytes;
}

static qbs_ref_status_t accumulate_q4(
    const qbs_block_q4_k_t *weight, const qbs_block_q8_k_t *activation,
    unsigned context, unsigned output, unsigned block, float *accumulator,
    qbs_trace_callback_t callback, void *opaque) {
  int8_t values[256];
  uint8_t scales[8];
  uint8_t mins[8];
  qbs_ref_decode_q4_k(weight, values, scales, mins);
  int64_t block_dot = 0;
  int64_t block_min = 0;
  for (unsigned group = 0; group < 8; ++group) {
    int32_t group_dot = 0;
    for (unsigned item = 0; item < 32; ++item) {
      const unsigned element = group * 32u + item;
      group_dot += (int32_t)values[element] * activation->qs[element];
    }
    const int32_t group_bsum =
        (int32_t)activation->bsums[group * 2u] +
        activation->bsums[group * 2u + 1u];
    block_dot += (int64_t)scales[group] * group_dot;
    block_min += (int64_t)mins[group] * group_bsum;
    if (callback != NULL) {
      const qbs_trace_event_t event = {
          .kind = QBS_TRACE_GROUP,
          .weight_profile = QBS_WEIGHT_PROFILE_Q4_K,
          .context = (uint8_t)context,
          .output = (uint8_t)output,
          .group = (uint8_t)group,
          .k_block = (uint16_t)block,
          .group_dot = group_dot,
          .group_aux = group_bsum,
          .group_scale = scales[group],
          .group_min = mins[group],
      };
      callback(&event, opaque);
    }
  }
  int32_t integer_dot;
  int32_t integer_min;
  if (!i64_to_i32(block_dot, &integer_dot) ||
      !i64_to_i32(block_min, &integer_min))
    return QBS_REF_INTEGER_OVERFLOW;

  const float before = *accumulator;
  const float dot_f = rounded_i32_to_f32(integer_dot);
  const float min_f = rounded_i32_to_f32(integer_min);
  const float sd =
      rounded_mul(qbs_ref_fp16_to_fp32(weight->d), activation->d);
  const float sm =
      rounded_mul(qbs_ref_fp16_to_fp32(weight->dmin), activation->d);
  const float positive = fmaf(sd, dot_f, before);
  *accumulator = fmaf(-sm, min_f, positive);
  if (callback != NULL) {
    const qbs_trace_event_t event = {
        .kind = QBS_TRACE_BLOCK,
        .weight_profile = QBS_WEIGHT_PROFILE_Q4_K,
        .context = (uint8_t)context,
        .output = (uint8_t)output,
        .k_block = (uint16_t)block,
        .block_dot = integer_dot,
        .block_aux = integer_min,
        .accumulator_before = before,
        .accumulator_after = *accumulator,
    };
    callback(&event, opaque);
  }
  return QBS_REF_OK;
}

static qbs_ref_status_t accumulate_q5(
    const qbs_block_q5_k_t *weight, const qbs_block_q8_k_t *activation,
    unsigned context, unsigned output, unsigned block, float *accumulator,
    qbs_trace_callback_t callback, void *opaque) {
  int8_t values[256];
  uint8_t scales[8];
  uint8_t mins[8];
  qbs_ref_decode_q5_k(weight, values, scales, mins);
  int64_t block_dot = 0;
  int64_t block_min = 0;
  for (unsigned group = 0; group < 8; ++group) {
    int32_t group_dot = 0;
    for (unsigned item = 0; item < 32; ++item) {
      const unsigned element = group * 32u + item;
      group_dot += (int32_t)values[element] * activation->qs[element];
    }
    const int32_t group_bsum =
        (int32_t)activation->bsums[group * 2u] +
        activation->bsums[group * 2u + 1u];
    block_dot += (int64_t)scales[group] * group_dot;
    block_min += (int64_t)mins[group] * group_bsum;
    if (callback != NULL) {
      const qbs_trace_event_t event = {
          .kind = QBS_TRACE_GROUP,
          .weight_profile = QBS_WEIGHT_PROFILE_Q5_K,
          .context = (uint8_t)context,
          .output = (uint8_t)output,
          .group = (uint8_t)group,
          .k_block = (uint16_t)block,
          .group_dot = group_dot,
          .group_aux = group_bsum,
          .group_scale = scales[group],
          .group_min = mins[group],
      };
      callback(&event, opaque);
    }
  }
  int32_t integer_dot;
  int32_t integer_min;
  if (!i64_to_i32(block_dot, &integer_dot) ||
      !i64_to_i32(block_min, &integer_min))
    return QBS_REF_INTEGER_OVERFLOW;

  const float before = *accumulator;
  const float dot_f = rounded_i32_to_f32(integer_dot);
  const float min_f = rounded_i32_to_f32(integer_min);
  const float sd =
      rounded_mul(qbs_ref_fp16_to_fp32(weight->d), activation->d);
  const float sm =
      rounded_mul(qbs_ref_fp16_to_fp32(weight->dmin), activation->d);
  const float positive = fmaf(sd, dot_f, before);
  *accumulator = fmaf(-sm, min_f, positive);
  if (callback != NULL) {
    const qbs_trace_event_t event = {
        .kind = QBS_TRACE_BLOCK,
        .weight_profile = QBS_WEIGHT_PROFILE_Q5_K,
        .context = (uint8_t)context,
        .output = (uint8_t)output,
        .k_block = (uint16_t)block,
        .block_dot = integer_dot,
        .block_aux = integer_min,
        .accumulator_before = before,
        .accumulator_after = *accumulator,
    };
    callback(&event, opaque);
  }
  return QBS_REF_OK;
}

static qbs_ref_status_t accumulate_q6(
    const qbs_block_q6_k_t *weight, const qbs_block_q8_k_t *activation,
    unsigned context, unsigned output, unsigned block, float *accumulator,
    qbs_trace_callback_t callback, void *opaque) {
  int8_t values[256];
  int8_t scales[16];
  qbs_ref_decode_q6_k(weight, values, scales);
  int64_t block_dot = 0;
  for (unsigned group = 0; group < 16; ++group) {
    int32_t group_dot = 0;
    for (unsigned item = 0; item < 16; ++item) {
      const unsigned element = group * 16u + item;
      group_dot += (int32_t)values[element] * activation->qs[element];
    }
    block_dot += (int64_t)scales[group] * group_dot;
    if (callback != NULL) {
      const qbs_trace_event_t event = {
          .kind = QBS_TRACE_GROUP,
          .weight_profile = QBS_WEIGHT_PROFILE_Q6_K,
          .context = (uint8_t)context,
          .output = (uint8_t)output,
          .group = (uint8_t)group,
          .k_block = (uint16_t)block,
          .group_dot = group_dot,
          .group_scale = scales[group],
      };
      callback(&event, opaque);
    }
  }
  int32_t integer_dot;
  if (!i64_to_i32(block_dot, &integer_dot))
    return QBS_REF_INTEGER_OVERFLOW;
  const float before = *accumulator;
  const float dot_f = rounded_i32_to_f32(integer_dot);
  const float sd =
      rounded_mul(qbs_ref_fp16_to_fp32(weight->d), activation->d);
  *accumulator = fmaf(sd, dot_f, before);
  if (callback != NULL) {
    const qbs_trace_event_t event = {
        .kind = QBS_TRACE_BLOCK,
        .weight_profile = QBS_WEIGHT_PROFILE_Q6_K,
        .context = (uint8_t)context,
        .output = (uint8_t)output,
        .k_block = (uint16_t)block,
        .block_dot = integer_dot,
        .accumulator_before = before,
        .accumulator_after = *accumulator,
    };
    callback(&event, opaque);
  }
  return QBS_REF_OK;
}

static qbs_ref_status_t accumulate_q3(
    const qbs_block_q3_k_t *weight, const qbs_block_q8_k_t *activation,
    unsigned context, unsigned output, unsigned block, float *accumulator,
    qbs_trace_callback_t callback, void *opaque) {
  int8_t values[256];
  int8_t scales[16];
  qbs_ref_decode_q3_k(weight, values, scales);
  int64_t block_dot = 0;
  for (unsigned group = 0; group < 16; ++group) {
    int32_t group_dot = 0;
    for (unsigned item = 0; item < 16; ++item) {
      const unsigned element = group * 16u + item;
      group_dot += (int32_t)values[element] * activation->qs[element];
    }
    block_dot += (int64_t)scales[group] * group_dot;
    if (callback != NULL) {
      const qbs_trace_event_t event = {
          .kind = QBS_TRACE_GROUP,
          .weight_profile = QBS_WEIGHT_PROFILE_Q3_K,
          .context = (uint8_t)context,
          .output = (uint8_t)output,
          .group = (uint8_t)group,
          .k_block = (uint16_t)block,
          .group_dot = group_dot,
          .group_scale = scales[group],
      };
      callback(&event, opaque);
    }
  }
  int32_t integer_dot;
  if (!i64_to_i32(block_dot, &integer_dot))
    return QBS_REF_INTEGER_OVERFLOW;
  const float before = *accumulator;
  const float dot_f = rounded_i32_to_f32(integer_dot);
  const float sd =
      rounded_mul(qbs_ref_fp16_to_fp32(weight->d), activation->d);
  *accumulator = fmaf(sd, dot_f, before);
  if (callback != NULL) {
    const qbs_trace_event_t event = {
        .kind = QBS_TRACE_BLOCK,
        .weight_profile = QBS_WEIGHT_PROFILE_Q3_K,
        .context = (uint8_t)context,
        .output = (uint8_t)output,
        .k_block = (uint16_t)block,
        .block_dot = integer_dot,
        .accumulator_before = before,
        .accumulator_after = *accumulator,
    };
    callback(&event, opaque);
  }
  return QBS_REF_OK;
}

static qbs_ref_status_t accumulate_q2(
    const qbs_block_q2_k_t *weight, const qbs_block_q8_k_t *activation,
    unsigned context, unsigned output, unsigned block, float *accumulator,
    qbs_trace_callback_t callback, void *opaque) {
  int8_t values[256];
  uint8_t scales[16];
  uint8_t mins[16];
  qbs_ref_decode_q2_k(weight, values, scales, mins);
  int64_t block_dot = 0;
  int64_t block_min = 0;
  for (unsigned group = 0; group < 16; ++group) {
    int32_t group_dot = 0;
    for (unsigned item = 0; item < 16; ++item) {
      const unsigned element = group * 16u + item;
      group_dot += (int32_t)values[element] * activation->qs[element];
    }
    const int32_t group_bsum = activation->bsums[group];
    block_dot += (int64_t)scales[group] * group_dot;
    block_min += (int64_t)mins[group] * group_bsum;
    if (callback != NULL) {
      const qbs_trace_event_t event = {
          .kind = QBS_TRACE_GROUP,
          .weight_profile = QBS_WEIGHT_PROFILE_Q2_K,
          .context = (uint8_t)context,
          .output = (uint8_t)output,
          .group = (uint8_t)group,
          .k_block = (uint16_t)block,
          .group_dot = group_dot,
          .group_aux = group_bsum,
          .group_scale = scales[group],
          .group_min = mins[group],
      };
      callback(&event, opaque);
    }
  }

  int32_t integer_dot;
  int32_t integer_min;
  if (!i64_to_i32(block_dot, &integer_dot) ||
      !i64_to_i32(block_min, &integer_min))
    return QBS_REF_INTEGER_OVERFLOW;

  const float before = *accumulator;
  const float dot_f = rounded_i32_to_f32(integer_dot);
  const float min_f = rounded_i32_to_f32(integer_min);
  const float sd =
      rounded_mul(qbs_ref_fp16_to_fp32(weight->d), activation->d);
  const float sm =
      rounded_mul(qbs_ref_fp16_to_fp32(weight->dmin), activation->d);
  const float positive = fmaf(sd, dot_f, before);
  *accumulator = fmaf(-sm, min_f, positive);
  if (callback != NULL) {
    const qbs_trace_event_t event = {
        .kind = QBS_TRACE_BLOCK,
        .weight_profile = QBS_WEIGHT_PROFILE_Q2_K,
        .context = (uint8_t)context,
        .output = (uint8_t)output,
        .k_block = (uint16_t)block,
        .block_dot = integer_dot,
        .block_aux = integer_min,
        .accumulator_before = before,
        .accumulator_after = *accumulator,
    };
    callback(&event, opaque);
  }
  return QBS_REF_OK;
}

static qbs_ref_status_t accumulate_scaled_block32(
    unsigned profile, qbs_fp16_t weight_d, const int8_t values[32],
    const qbs_block_q8_0_t *activation, unsigned context, unsigned output,
    unsigned block, float *accumulator, qbs_trace_callback_t callback,
    void *opaque) {
  int32_t integer_dot = 0;
  for (unsigned element = 0; element < 32; ++element)
    integer_dot += (int32_t)values[element] * activation->qs[element];

  if (callback != NULL) {
    const qbs_trace_event_t group_event = {
        .kind = QBS_TRACE_GROUP,
        .weight_profile = (uint8_t)profile,
        .context = (uint8_t)context,
        .output = (uint8_t)output,
        .group = 0,
        .k_block = (uint16_t)block,
        .group_dot = integer_dot,
        .group_scale = 1,
    };
    callback(&group_event, opaque);
  }

  const float before = *accumulator;
  const float dot_f = rounded_i32_to_f32(integer_dot);
  const float sd = rounded_mul(qbs_ref_fp16_to_fp32(weight_d),
                               qbs_ref_fp16_to_fp32(activation->d));
  *accumulator = fmaf(sd, dot_f, before);
  if (callback != NULL) {
    const qbs_trace_event_t block_event = {
        .kind = QBS_TRACE_BLOCK,
        .weight_profile = (uint8_t)profile,
        .context = (uint8_t)context,
        .output = (uint8_t)output,
        .k_block = (uint16_t)block,
        .block_dot = integer_dot,
        .accumulator_before = before,
        .accumulator_after = *accumulator,
    };
    callback(&block_event, opaque);
  }
  return QBS_REF_OK;
}

static qbs_ref_status_t accumulate_q4_0(
    const qbs_block_q4_0_t *weight, const qbs_block_q8_0_t *activation,
    unsigned context, unsigned output, unsigned block, float *accumulator,
    qbs_trace_callback_t callback, void *opaque) {
  int8_t values[QBS_Q4_0_BLOCK_ELEMENTS];
  qbs_ref_decode_q4_0(weight, values);
  return accumulate_scaled_block32(
      QBS_WEIGHT_PROFILE_Q4_0, weight->d, values, activation, context, output,
      block, accumulator, callback, opaque);
}

static qbs_ref_status_t accumulate_q5_0(
    const qbs_block_q5_0_t *weight, const qbs_block_q8_0_t *activation,
    unsigned context, unsigned output, unsigned block, float *accumulator,
    qbs_trace_callback_t callback, void *opaque) {
  int8_t values[QBS_Q5_0_BLOCK_ELEMENTS];
  qbs_ref_decode_q5_0(weight, values);
  return accumulate_scaled_block32(
      QBS_WEIGHT_PROFILE_Q5_0, weight->d, values, activation, context, output,
      block, accumulator, callback, opaque);
}

static qbs_ref_status_t accumulate_iq4_nl(
    const qbs_block_iq4_nl_t *weight, const qbs_block_q8_0_t *activation,
    unsigned context, unsigned output, unsigned block, float *accumulator,
    qbs_trace_callback_t callback, void *opaque) {
  int8_t values[QBS_IQ4_NL_BLOCK_ELEMENTS];
  qbs_ref_decode_iq4_nl(weight, values);
  return accumulate_scaled_block32(
      QBS_WEIGHT_PROFILE_IQ4_NL, weight->d, values, activation, context,
      output, block, accumulator, callback, opaque);
}

static qbs_ref_status_t accumulate_q8_0(
    const qbs_block_q8_0_t *weight, const qbs_block_q8_0_t *activation,
    unsigned context, unsigned output, unsigned block, float *accumulator,
    qbs_trace_callback_t callback, void *opaque) {
  int32_t integer_dot = 0;
  for (unsigned element = 0; element < QBS_Q8_0_WEIGHT_BLOCK_ELEMENTS;
       ++element)
    integer_dot += (int32_t)weight->qs[element] * activation->qs[element];

  if (callback != NULL) {
    const qbs_trace_event_t group_event = {
        .kind = QBS_TRACE_GROUP,
        .weight_profile = QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
        .context = (uint8_t)context,
        .output = (uint8_t)output,
        .group = 0,
        .k_block = (uint16_t)block,
        .group_dot = integer_dot,
        .group_scale = 1,
    };
    callback(&group_event, opaque);
  }

  const float before = *accumulator;
  const float dot_f = rounded_i32_to_f32(integer_dot);
  const float sd = rounded_mul(qbs_ref_fp16_to_fp32(weight->d),
                               qbs_ref_fp16_to_fp32(activation->d));
  *accumulator = fmaf(sd, dot_f, before);
  if (callback != NULL) {
    const qbs_trace_event_t block_event = {
        .kind = QBS_TRACE_BLOCK,
        .weight_profile = QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
        .context = (uint8_t)context,
        .output = (uint8_t)output,
        .k_block = (uint16_t)block,
        .block_dot = integer_dot,
        .accumulator_before = before,
        .accumulator_after = *accumulator,
    };
    callback(&block_event, opaque);
  }
  return QBS_REF_OK;
}

static qbs_ref_status_t qbs_ref_execute_data(
    const qbs_descriptor_t *descriptor, unsigned m, unsigned vd,
    unsigned vlen_bits, uint64_t activation_base, const void *weight_data,
    size_t weight_bytes, const void *activation_data, size_t activation_bytes,
    float *destination, size_t destination_elements,
    qbs_trace_callback_t trace_callback, void *trace_opaque,
    qbs_ref_result_t *result) {
  if (weight_data == NULL || activation_data == NULL || destination == NULL ||
      result == NULL)
    return QBS_REF_BAD_ARGUMENT;
  qbs_ref_status_t status = qbs_ref_validate_descriptor(
      descriptor, m, vd, vlen_bits, activation_base);
  if (status != QBS_REF_OK) return status;

  const qbs_descriptor_fields_t fields =
      qbs_unpack_descriptor_header(descriptor->header);
  const size_t required_weight = qbs_ref_weight_storage_bytes(
      fields.weight_profile, fields.weight_layout, fields.n, fields.k_blocks);
  const size_t required_activation =
      qbs_ref_activation_storage_bytes_for_profile(
          fields.activation_profile, fields.activation_layout, m,
          fields.k_blocks);
  if (weight_bytes < required_weight || activation_bytes < required_activation)
    return QBS_REF_BUFFER_SIZE;

  const unsigned elements_per_register = vlen_bits / 32u;
  const unsigned registers = destination_register_count(m);
  size_t required_output;
  if (!size_mul(registers, elements_per_register, &required_output) ||
      destination_elements < required_output)
    return QBS_REF_OUTPUT_SIZE;

  float *pending_destination = calloc(required_output, sizeof(float));
  if (pending_destination == NULL) return QBS_REF_ALLOCATION_FAILURE;

  const int old_round = fegetround();
  if (fesetround(FE_TONEAREST) != 0) {
    free(pending_destination);
    return QBS_REF_BAD_ARGUMENT;
  }
  feclearexcept(FE_ALL_EXCEPT);
  const size_t block_bytes = weight_block_bytes(fields.weight_profile);
  for (unsigned block = 0; block < fields.k_blocks; ++block) {
    uint8_t activation[QBS_MAX_M][QBS_MAX_ACTIVATION_BLOCK_BYTES];
    for (unsigned context = 0; context < m; ++context) {
      read_activation_block(fields.activation_profile,
                            fields.activation_layout, activation_data,
                            context, block, fields.k_blocks,
                            activation[context]);
    }
    for (unsigned output = 0; output < fields.n; ++output) {
      const uint8_t *address = weight_block_address(
          weight_data, fields.weight_layout, output, block, fields.k_blocks,
          block_bytes);
      if (fields.weight_profile == QBS_WEIGHT_PROFILE_Q4_K) {
        qbs_block_q4_k_t weight;
        memcpy(&weight, address, sizeof(weight));
        for (unsigned context = 0; context < m; ++context) {
          float *accumulator =
              &pending_destination[(size_t)context * elements_per_register +
                                   output];
          status = accumulate_q4(
                                 &weight,
                                 (const qbs_block_q8_k_t *)activation[context],
                                 context,
                                 output, block, accumulator, trace_callback,
                                 trace_opaque);
          if (status != QBS_REF_OK) goto done;
        }
      } else if (fields.weight_profile == QBS_WEIGHT_PROFILE_Q5_K) {
        qbs_block_q5_k_t weight;
        memcpy(&weight, address, sizeof(weight));
        for (unsigned context = 0; context < m; ++context) {
          float *accumulator =
              &pending_destination[(size_t)context * elements_per_register +
                                   output];
          status = accumulate_q5(
              &weight, (const qbs_block_q8_k_t *)activation[context], context,
              output, block, accumulator, trace_callback, trace_opaque);
          if (status != QBS_REF_OK) goto done;
        }
      } else if (fields.weight_profile == QBS_WEIGHT_PROFILE_Q6_K) {
        qbs_block_q6_k_t weight;
        memcpy(&weight, address, sizeof(weight));
        for (unsigned context = 0; context < m; ++context) {
          float *accumulator =
              &pending_destination[(size_t)context * elements_per_register +
                                   output];
          status = accumulate_q6(
                                 &weight,
                                 (const qbs_block_q8_k_t *)activation[context],
                                 context,
                                 output, block, accumulator, trace_callback,
                                 trace_opaque);
          if (status != QBS_REF_OK) goto done;
        }
      } else if (fields.weight_profile == QBS_WEIGHT_PROFILE_Q3_K) {
        qbs_block_q3_k_t weight;
        memcpy(&weight, address, sizeof(weight));
        for (unsigned context = 0; context < m; ++context) {
          float *accumulator =
              &pending_destination[(size_t)context * elements_per_register +
                                   output];
          status = accumulate_q3(
              &weight, (const qbs_block_q8_k_t *)activation[context], context,
              output, block, accumulator, trace_callback, trace_opaque);
          if (status != QBS_REF_OK) goto done;
        }
      } else if (fields.weight_profile == QBS_WEIGHT_PROFILE_Q2_K) {
        qbs_block_q2_k_t weight;
        memcpy(&weight, address, sizeof(weight));
        for (unsigned context = 0; context < m; ++context) {
          float *accumulator =
              &pending_destination[(size_t)context * elements_per_register +
                                   output];
          status = accumulate_q2(
              &weight, (const qbs_block_q8_k_t *)activation[context], context,
              output, block, accumulator, trace_callback, trace_opaque);
          if (status != QBS_REF_OK) goto done;
        }
      } else if (fields.weight_profile ==
                 QBS_WEIGHT_PROFILE_Q8_0_WEIGHT) {
        qbs_block_q8_0_t weight;
        memcpy(&weight, address, sizeof(weight));
        for (unsigned context = 0; context < m; ++context) {
          float *accumulator =
              &pending_destination[(size_t)context * elements_per_register +
                                   output];
          status = accumulate_q8_0(
              &weight, (const qbs_block_q8_0_t *)activation[context], context,
              output, block, accumulator, trace_callback, trace_opaque);
          if (status != QBS_REF_OK) goto done;
        }
      } else if (fields.weight_profile == QBS_WEIGHT_PROFILE_Q5_0) {
        qbs_block_q5_0_t weight;
        memcpy(&weight, address, sizeof(weight));
        for (unsigned context = 0; context < m; ++context) {
          float *accumulator =
              &pending_destination[(size_t)context * elements_per_register +
                                   output];
          status = accumulate_q5_0(
              &weight, (const qbs_block_q8_0_t *)activation[context], context,
              output, block, accumulator, trace_callback, trace_opaque);
          if (status != QBS_REF_OK) goto done;
        }
      } else if (fields.weight_profile == QBS_WEIGHT_PROFILE_IQ4_NL) {
        qbs_block_iq4_nl_t weight;
        memcpy(&weight, address, sizeof(weight));
        for (unsigned context = 0; context < m; ++context) {
          float *accumulator =
              &pending_destination[(size_t)context * elements_per_register +
                                   output];
          status = accumulate_iq4_nl(
              &weight, (const qbs_block_q8_0_t *)activation[context], context,
              output, block, accumulator, trace_callback, trace_opaque);
          if (status != QBS_REF_OK) goto done;
        }
      } else {
        qbs_block_q4_0_t weight;
        memcpy(&weight, address, sizeof(weight));
        for (unsigned context = 0; context < m; ++context) {
          float *accumulator =
              &pending_destination[(size_t)context * elements_per_register +
                                   output];
          status = accumulate_q4_0(
              &weight, (const qbs_block_q8_0_t *)activation[context], context,
              output, block, accumulator, trace_callback, trace_opaque);
          if (status != QBS_REF_OK) goto done;
        }
      }
    }
  }

done:;
  const uint32_t command_fflags = host_fp_flags();
  if (old_round != -1) (void)fesetround(old_round);
  if (status == QBS_REF_OK) {
    for (unsigned context = 0; context < m; ++context) {
      memcpy(destination + (size_t)context * elements_per_register,
             pending_destination + (size_t)context * elements_per_register,
             elements_per_register * sizeof(float));
    }
    result->destination_registers = registers;
    result->destination_elements_per_register = elements_per_register;
    result->active_outputs = m * fields.n;
    result->fflags = command_fflags;
  }
  free(pending_destination);
  return status;
}

void qbs_ref_activation_context_reset(qbs_ref_activation_context_t *context) {
  if (context != NULL) memset(context, 0, sizeof(*context));
}

qbs_ref_status_t qbs_ref_validate_activation_context(
    const qbs_ref_activation_context_t *context,
    const qbs_descriptor_fields_t *fields, unsigned m) {
  if (fields == NULL) return QBS_REF_BAD_ARGUMENT;
  if (fields->activation_access == QBS_ACTIVATION_ACCESS_DIRECT)
    return QBS_REF_OK;
  if (context == NULL) return QBS_REF_CONTEXT_INVALID;
  if (fields->activation_access == QBS_ACTIVATION_ACCESS_FILL)
    return QBS_REF_OK;
  if (!context->valid || context->context_id != fields->context_id)
    return QBS_REF_CONTEXT_INVALID;
  if (context->generation != fields->context_generation)
    return QBS_REF_CONTEXT_GENERATION;
  if (context->activation_profile != fields->activation_profile ||
      context->activation_layout != fields->activation_layout ||
      context->m != m || context->k_blocks != fields->k_blocks)
    return QBS_REF_CONTEXT_METADATA;
  return QBS_REF_OK;
}

qbs_ref_status_t qbs_ref_execute_with_context(
    qbs_ref_activation_context_t *context,
    const qbs_descriptor_t *descriptor, unsigned m, unsigned vd,
    unsigned vlen_bits, uint64_t activation_base, const void *weight_data,
    size_t weight_bytes, const void *activation_data, size_t activation_bytes,
    float *destination, size_t destination_elements,
    qbs_trace_callback_t trace_callback, void *trace_opaque,
    qbs_ref_result_t *result) {
  qbs_ref_status_t status = qbs_ref_validate_descriptor(
      descriptor, m, vd, vlen_bits, activation_base);
  if (status != QBS_REF_OK) return status;

  const qbs_descriptor_fields_t fields =
      qbs_unpack_descriptor_header(descriptor->header);
  status = qbs_ref_validate_activation_context(context, &fields, m);
  if (status != QBS_REF_OK) return status;
  const size_t required_activation =
      qbs_ref_activation_storage_bytes_for_profile(
          fields.activation_profile, fields.activation_layout, m,
          fields.k_blocks);

  if (fields.activation_access == QBS_ACTIVATION_ACCESS_DIRECT) {
    return qbs_ref_execute_data(
        descriptor, m, vd, vlen_bits, activation_base, weight_data,
        weight_bytes, activation_data, activation_bytes, destination,
        destination_elements, trace_callback, trace_opaque, result);
  }

  if (fields.activation_access == QBS_ACTIVATION_ACCESS_FILL) {
    // A new FILL supersedes the old generation as soon as the command is
    // accepted. Any later read/compute failure therefore leaves no reusable
    // context, matching the RTL's fill-begin/commit transaction boundary.
    context->valid = 0;
    if (activation_data == NULL || activation_bytes < required_activation)
      return QBS_REF_BUFFER_SIZE;

    status = qbs_ref_execute_data(
        descriptor, m, vd, vlen_bits, activation_base, weight_data,
        weight_bytes, activation_data, activation_bytes, destination,
        destination_elements, trace_callback, trace_opaque, result);
    if (status != QBS_REF_OK) return status;

    memcpy(context->data, activation_data, required_activation);
    context->context_id = fields.context_id;
    context->generation = fields.context_generation;
    context->activation_profile = fields.activation_profile;
    context->activation_layout = fields.activation_layout;
    context->m = (uint8_t)m;
    context->k_blocks = fields.k_blocks;
    context->valid = 1;
    return QBS_REF_OK;
  }

  status = qbs_ref_execute_data(
      descriptor, m, vd, vlen_bits, activation_base, weight_data,
      weight_bytes, context->data, required_activation, destination,
      destination_elements, trace_callback, trace_opaque, result);
  if (status == QBS_REF_OK &&
      fields.activation_access == QBS_ACTIVATION_ACCESS_RELEASE)
    context->valid = 0;
  return status;
}

qbs_ref_status_t qbs_ref_execute(
    const qbs_descriptor_t *descriptor, unsigned m, unsigned vd,
    unsigned vlen_bits, uint64_t activation_base, const void *weight_data,
    size_t weight_bytes, const void *activation_data, size_t activation_bytes,
    float *destination, size_t destination_elements,
    qbs_trace_callback_t trace_callback, void *trace_opaque,
    qbs_ref_result_t *result) {
  return qbs_ref_execute_with_context(
      NULL, descriptor, m, vd, vlen_bits, activation_base, weight_data,
      weight_bytes, activation_data, activation_bytes, destination,
      destination_elements, trace_callback, trace_opaque, result);
}
