#include "qbs_ref.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned failures;

#define CHECK(condition)                                                     \
  do {                                                                       \
    if (!(condition)) {                                                      \
      fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
      ++failures;                                                            \
    }                                                                        \
  } while (0)

#define CHECK_STATUS(expression, expected)                                  \
  do {                                                                       \
    const qbs_ref_status_t actual_status = (expression);                     \
    if (actual_status != (expected)) {                                       \
      fprintf(stderr, "FAIL %s:%d: %s returned %s, expected %s\n",         \
              __FILE__, __LINE__, #expression,                              \
              qbs_ref_status_string(actual_status),                         \
              qbs_ref_status_string(expected));                             \
      ++failures;                                                            \
    }                                                                        \
  } while (0)

typedef struct {
  unsigned groups;
  unsigned blocks;
} trace_counts_t;

static void count_trace(const qbs_trace_event_t *event, void *opaque) {
  trace_counts_t *counts = (trace_counts_t *)opaque;
  if (event->kind == QBS_TRACE_GROUP) {
    ++counts->groups;
  } else if (event->kind == QBS_TRACE_BLOCK) {
    ++counts->blocks;
  } else {
    CHECK(0);
  }
}

static qbs_descriptor_v1_t make_descriptor(unsigned weight_profile,
                                           unsigned activation_profile,
                                           unsigned weight_layout,
                                           unsigned activation_layout,
                                           unsigned n, unsigned k_blocks) {
  const qbs_descriptor_fields_t fields = {
      .descriptor_version = QBS_DESCRIPTOR_VERSION,
      .weight_profile = (uint8_t)weight_profile,
      .activation_profile = (uint8_t)activation_profile,
      .weight_layout = (uint8_t)weight_layout,
      .activation_layout = (uint8_t)activation_layout,
      .n = (uint8_t)n,
      .k_blocks = (uint16_t)k_blocks,
  };
  const qbs_descriptor_v1_t descriptor = {
      .header = qbs_pack_descriptor_header(&fields),
      .weight_base = UINT64_C(0x1000),
  };
  return descriptor;
}

static uint32_t float_bits(float value) {
  uint32_t bits;
  memcpy(&bits, &value, sizeof(bits));
  return bits;
}

static int llama_nearest_int(float value) {
  volatile float biased = value + 12582912.0f;
  uint32_t bits;
  memcpy(&bits, (const void *)&biased, sizeof(bits));
  return (int)(bits & UINT32_C(0x007fffff)) - 0x00400000;
}

static void llama_quantize_q8_k(const float input[256],
                                qbs_block_q8_k_t *output) {
  float maximum = 0.0f;
  float absolute_maximum = 0.0f;
  for (unsigned element = 0; element < 256; ++element) {
    const float absolute = fabsf(input[element]);
    if (absolute > absolute_maximum) {
      absolute_maximum = absolute;
      maximum = input[element];
    }
  }
  if (absolute_maximum == 0.0f) {
    memset(output, 0, sizeof(*output));
    return;
  }
  volatile float inverse_scale = -127.0f / maximum;
  for (unsigned element = 0; element < 256; ++element) {
    volatile float scaled = inverse_scale * input[element];
    int quantized = llama_nearest_int(scaled);
    if (quantized > 127) quantized = 127;
    output->qs[element] = (int8_t)quantized;
  }
  for (unsigned subgroup = 0; subgroup < 16; ++subgroup) {
    int sum = 0;
    for (unsigned item = 0; item < 16; ++item)
      sum += output->qs[subgroup * 16u + item];
    output->bsums[subgroup] = (int16_t)sum;
  }
  volatile float scale = 1.0f / inverse_scale;
  output->d = scale;
}

static void test_abi(void) {
  const qbs_descriptor_fields_t fields = {
      .descriptor_version = 1,
      .weight_profile = QBS_WEIGHT_PROFILE_Q6_K,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
      .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
      .activation_layout = QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED,
      .n = 32,
      .k_blocks = 256,
  };
  const uint64_t header = qbs_pack_descriptor_header(&fields);
  const qbs_descriptor_fields_t decoded =
      qbs_unpack_descriptor_header(header);
  CHECK(decoded.descriptor_version == fields.descriptor_version);
  CHECK(decoded.weight_profile == fields.weight_profile);
  CHECK(decoded.activation_profile == fields.activation_profile);
  CHECK(decoded.weight_layout == fields.weight_layout);
  CHECK(decoded.activation_layout == fields.activation_layout);
  CHECK(decoded.n == fields.n);
  CHECK(decoded.k_blocks == fields.k_blocks);
  CHECK((header >> 33) == 0);

  CHECK(qbs_encode_qbexec(8, 10, 11, 4) == UINT32_C(0x06b5045b));
  CHECK(qbs_encode_qbexec(1, 2, 3, 1) == UINT32_C(0x003100db));
  CHECK(qbs_encode_qbinfo(6, 5) == UINT32_C(0x0002935b));

  const uint64_t info0 = qbs_ref_capability_word(0, 1024);
  CHECK(((info0 >> 0) & 0xffu) == QBS_ARCH_VERSION);
  CHECK(((info0 >> 8) & 0xffu) == QBS_DESCRIPTOR_VERSION);
  CHECK(((info0 >> 16) & 0xffu) == QBS_DESCRIPTOR_BYTES);
  CHECK(((info0 >> 24) & 0x3u) + 1u == QBS_MAX_M);
  CHECK(((info0 >> 26) & 0x1fu) + 1u == QBS_MAX_N);
  CHECK(((info0 >> 31) & 0xffu) + 1u == QBS_MAX_K_BLOCKS);
  CHECK(((info0 >> 39) & 0xfu) == QBS_NUMERICAL_CONTRACT_VERSION);
  CHECK(((info0 >> 43) & 0x1fu) == 0x1fu);
  CHECK(qbs_ref_capability_word(0, 256) != info0);
  CHECK(qbs_ref_capability_word(0xff, 1024) == 0);
}

static void test_descriptor_validation(void) {
  qbs_descriptor_v1_t descriptor = make_descriptor(
      QBS_WEIGHT_PROFILE_Q4_K, QBS_ACTIVATION_PROFILE_Q8_K,
      QBS_WEIGHT_LAYOUT_ROW_MAJOR, QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 32, 64);
  CHECK_STATUS(qbs_ref_validate_descriptor(&descriptor, 1, 3, 1024, 0x2000),
               QBS_REF_OK);

  uint8_t storage[sizeof(descriptor) + QBS_DESCRIPTOR_BYTES];
  memcpy(storage + 1, &descriptor, sizeof(descriptor));
  CHECK_STATUS(qbs_ref_validate_descriptor(
                   (const qbs_descriptor_v1_t *)(const void *)(storage + 1),
                   1, 3, 1024, 0x2000),
               QBS_REF_DESCRIPTOR_ALIGNMENT);

  qbs_descriptor_v1_t invalid = descriptor;
  invalid.header = (invalid.header & ~UINT64_C(0x0f)) | 2u;
  CHECK_STATUS(qbs_ref_validate_descriptor(&invalid, 1, 3, 1024, 0x2000),
               QBS_REF_DESCRIPTOR_VERSION);
  invalid = descriptor;
  invalid.header |= UINT64_C(1) << 33;
  CHECK_STATUS(qbs_ref_validate_descriptor(&invalid, 1, 3, 1024, 0x2000),
               QBS_REF_DESCRIPTOR_RESERVED);
  invalid = descriptor;
  invalid.header = (invalid.header & ~(UINT64_C(0x0f) << 4)) |
                   (UINT64_C(15) << 4);
  CHECK_STATUS(qbs_ref_validate_descriptor(&invalid, 1, 3, 1024, 0x2000),
               QBS_REF_WEIGHT_PROFILE);

  invalid = make_descriptor(QBS_WEIGHT_PROFILE_Q4_K,
                            QBS_ACTIVATION_PROFILE_Q8_K,
                            QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                            QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED, 8, 1);
  CHECK_STATUS(qbs_ref_validate_descriptor(&invalid, 1, 0, 1024, 0x2000),
               QBS_REF_ACTIVATION_LAYOUT);
  invalid = make_descriptor(QBS_WEIGHT_PROFILE_Q4_K,
                            QBS_ACTIVATION_PROFILE_Q8_K,
                            QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                            QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 9, 1);
  CHECK_STATUS(qbs_ref_validate_descriptor(&invalid, 1, 0, 256, 0x2000),
               QBS_REF_N_RANGE);
  invalid = make_descriptor(QBS_WEIGHT_PROFILE_Q4_K,
                            QBS_ACTIVATION_PROFILE_Q8_K,
                            QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                            QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 8,
                            QBS_MAX_K_BLOCKS);
  CHECK_STATUS(qbs_ref_validate_descriptor(&invalid, 1, 0, 1024, 0x2000),
               QBS_REF_OK);
  CHECK_STATUS(qbs_ref_validate_descriptor(&descriptor, 0, 0, 1024, 0x2000),
               QBS_REF_M_RANGE);
  CHECK_STATUS(qbs_ref_validate_descriptor(&descriptor, 1, 0, 1000, 0x2000),
               QBS_REF_VLEN);
  CHECK_STATUS(qbs_ref_validate_descriptor(&descriptor, 2, 1, 1024, 0x2000),
               QBS_REF_VD_ALIGNMENT);
  invalid = descriptor;
  invalid.weight_base = UINT64_C(0x1001);
  CHECK_STATUS(qbs_ref_validate_descriptor(&invalid, 1, 0, 1024, 0x2000),
               QBS_REF_BASE_ALIGNMENT);
  CHECK_STATUS(qbs_ref_validate_descriptor(&descriptor, 1, 0, 1024, 0x2002),
               QBS_REF_BASE_ALIGNMENT);
  invalid = descriptor;
  invalid.weight_base = UINT64_MAX - 1u;
  CHECK_STATUS(qbs_ref_validate_descriptor(&invalid, 1, 0, 1024, 0x2000),
               QBS_REF_ADDRESS_OVERFLOW);
}

static void test_q8_quantization(void) {
  float input[256];
  qbs_block_q8_k_t expected;
  qbs_block_q8_k_t actual;

  memset(input, 0, sizeof(input));
  memset(&actual, 0xa5, sizeof(actual));
  CHECK_STATUS(qbs_ref_quantize_q8_k(input, 256, &actual, 1), QBS_REF_OK);
  qbs_block_q8_k_t zero;
  memset(&zero, 0, sizeof(zero));
  CHECK(memcmp(&actual, &zero, sizeof(actual)) == 0);

  for (unsigned element = 0; element < 256; ++element)
    input[element] = (float)((int)(element % 29u) - 14) / 7.0f;
  input[0] = 3.0f;
  input[1] = -3.0f;
  llama_quantize_q8_k(input, &expected);
  CHECK_STATUS(qbs_ref_quantize_q8_k(input, 256, &actual, 1), QBS_REF_OK);
  CHECK(memcmp(&actual, &expected, sizeof(actual)) == 0);
  CHECK(float_bits(actual.d) == float_bits(expected.d));
}

static void test_q4_decode(void) {
  qbs_block_q4_k_t block;
  memset(&block, 0, sizeof(block));
  block.scales[0] = 1u | (0u << 6);
  block.scales[1] = 2u | (1u << 6);
  block.scales[2] = 3u | (2u << 6);
  block.scales[3] = 4u | (3u << 6);
  block.scales[4] = 5u | (3u << 6);
  block.scales[5] = 6u | (2u << 6);
  block.scales[6] = 7u | (1u << 6);
  block.scales[7] = 8u | (0u << 6);
  block.scales[8] = 0x91u;
  block.scales[9] = 0xa2u;
  block.scales[10] = 0xb3u;
  block.scales[11] = 0xc4u;
  for (unsigned index = 0; index < 128; ++index) {
    const uint8_t low = (uint8_t)(index & 0x0fu);
    block.qs[index] = (uint8_t)(low | ((15u - low) << 4));
  }

  int8_t values[256];
  uint8_t scales[8];
  uint8_t mins[8];
  qbs_ref_decode_q4_k(&block, values, scales, mins);
  const uint8_t expected_scales[8] = {1, 2, 3, 4, 1, 18, 35, 52};
  const uint8_t expected_mins[8] = {5, 6, 7, 8, 57, 42, 27, 12};
  CHECK(memcmp(scales, expected_scales, sizeof(scales)) == 0);
  CHECK(memcmp(mins, expected_mins, sizeof(mins)) == 0);
  for (unsigned packet = 0; packet < 4; ++packet) {
    for (unsigned lane = 0; lane < 32; ++lane) {
      const int8_t low = (int8_t)(lane & 0x0fu);
      CHECK(values[packet * 64u + lane] == low);
      CHECK(values[packet * 64u + 32u + lane] == 15 - low);
    }
  }
}

static void test_q5_decode(void) {
  qbs_block_q5_k_t block;
  memset(&block, 0, sizeof(block));
  for (unsigned index = 0; index < sizeof(block.scales); ++index)
    block.scales[index] = (uint8_t)(index * 19u + 3u);

  int8_t expected[QBS_Q5_K_BLOCK_ELEMENTS];
  for (unsigned packet = 0; packet < 4; ++packet) {
    for (unsigned lane = 0; lane < 32; ++lane) {
      const unsigned low_element = packet * 64u + lane;
      const unsigned high_element = low_element + 32u;
      const uint8_t low_value = (uint8_t)((packet * 7u + lane) & 0x1fu);
      const uint8_t high_value =
          (uint8_t)((packet * 11u + 31u - lane) & 0x1fu);
      expected[low_element] = (int8_t)low_value;
      expected[high_element] = (int8_t)high_value;
      block.qs[packet * 32u + lane] =
          (uint8_t)((low_value & 0x0fu) | ((high_value & 0x0fu) << 4));
      block.qh[lane] |= (uint8_t)(((low_value >> 4) & 1u) << (2u * packet));
      block.qh[lane] |=
          (uint8_t)(((high_value >> 4) & 1u) << (2u * packet + 1u));
    }
  }

  int8_t actual[QBS_Q5_K_BLOCK_ELEMENTS];
  uint8_t scales[8];
  uint8_t mins[8];
  qbs_ref_decode_q5_k(&block, actual, scales, mins);
  CHECK(memcmp(actual, expected, sizeof(actual)) == 0);
  for (unsigned group = 0; group < 8; ++group) {
    uint8_t expected_scale;
    uint8_t expected_min;
    if (group < 4) {
      expected_scale = block.scales[group] & 0x3fu;
      expected_min = block.scales[group + 4u] & 0x3fu;
    } else {
      expected_scale = (block.scales[group + 4u] & 0x0fu) |
                       ((block.scales[group - 4u] >> 6) << 4);
      expected_min = (block.scales[group + 4u] >> 4) |
                     ((block.scales[group] >> 6) << 4);
    }
    CHECK(scales[group] == expected_scale);
    CHECK(mins[group] == expected_min);
  }
}

static void encode_q6(const int8_t values[256], qbs_block_q6_k_t *block) {
  memset(block->ql, 0, sizeof(block->ql));
  memset(block->qh, 0, sizeof(block->qh));
  for (unsigned half = 0; half < 2; ++half) {
    for (unsigned lane = 0; lane < 32; ++lane) {
      const unsigned base = half * 128u;
      const uint8_t q0 = (uint8_t)(values[base + lane] + 32);
      const uint8_t q1 = (uint8_t)(values[base + 32u + lane] + 32);
      const uint8_t q2 = (uint8_t)(values[base + 64u + lane] + 32);
      const uint8_t q3 = (uint8_t)(values[base + 96u + lane] + 32);
      block->ql[half * 64u + lane] =
          (uint8_t)((q0 & 0x0fu) | ((q2 & 0x0fu) << 4));
      block->ql[half * 64u + 32u + lane] =
          (uint8_t)((q1 & 0x0fu) | ((q3 & 0x0fu) << 4));
      block->qh[half * 32u + lane] =
          (uint8_t)(((q0 >> 4) & 3u) | (((q1 >> 4) & 3u) << 2) |
                    (((q2 >> 4) & 3u) << 4) |
                    (((q3 >> 4) & 3u) << 6));
    }
  }
}

static void test_q6_decode(void) {
  qbs_block_q6_k_t block;
  int8_t expected[256];
  for (unsigned element = 0; element < 256; ++element)
    expected[element] = (int8_t)((int)(element % 64u) - 32);
  encode_q6(expected, &block);
  for (unsigned group = 0; group < 16; ++group)
    block.scales[group] = (int8_t)((int)group - 8);
  int8_t actual[256];
  int8_t scales[16];
  qbs_ref_decode_q6_k(&block, actual, scales);
  CHECK(memcmp(actual, expected, sizeof(actual)) == 0);
  CHECK(memcmp(scales, block.scales, sizeof(scales)) == 0);
}

static void set_q3_scale(qbs_block_q3_k_t *block, unsigned group,
                         int8_t scale) {
  const unsigned raw = (unsigned)(scale + 32);
  const unsigned within = group & 3u;
  const unsigned region = group >> 2;
  const unsigned low_index = (region & 1u) * 4u + within;
  if (region < 2u)
    block->scales[low_index] |= (uint8_t)(raw & 0x0fu);
  else
    block->scales[low_index] |= (uint8_t)((raw & 0x0fu) << 4);
  block->scales[8u + within] |=
      (uint8_t)(((raw >> 4) & 0x03u) << (2u * region));
}

static void test_q3_decode(void) {
  qbs_block_q3_k_t block;
  memset(&block, 0, sizeof(block));
  int8_t expected[QBS_Q3_K_BLOCK_ELEMENTS];
  int8_t expected_scales[16];
  for (unsigned group = 0; group < 16; ++group) {
    expected_scales[group] = (int8_t)((int)(group * 4u) - 32);
    set_q3_scale(&block, group, expected_scales[group]);
  }
  for (unsigned packet = 0; packet < 8; ++packet) {
    for (unsigned lane = 0; lane < 32; ++lane) {
      const unsigned element = packet * 32u + lane;
      const int8_t value = (int8_t)((int)((packet + lane) & 7u) - 4);
      expected[element] = value;
      const unsigned low = value < 0 ? (unsigned)(value + 4) : (unsigned)value;
      block.qs[(packet / 4u) * 32u + lane] |=
          (uint8_t)(low << (2u * (packet & 3u)));
      if (value >= 0) block.hmask[lane] |= (uint8_t)(1u << packet);
    }
  }
  int8_t actual[QBS_Q3_K_BLOCK_ELEMENTS];
  int8_t actual_scales[16];
  qbs_ref_decode_q3_k(&block, actual, actual_scales);
  CHECK(memcmp(actual, expected, sizeof(actual)) == 0);
  CHECK(memcmp(actual_scales, expected_scales, sizeof(actual_scales)) == 0);
}

static void test_q4_0_decode(void) {
  qbs_block_q4_0_t block = {.d = UINT16_C(0x3c00)};
  for (unsigned index = 0; index < 16; ++index)
    block.qs[index] = (uint8_t)(index | ((15u - index) << 4));
  int8_t values[32];
  qbs_ref_decode_q4_0(&block, values);
  for (unsigned index = 0; index < 16; ++index) {
    CHECK(values[index] == (int8_t)index - 8);
    CHECK(values[index + 16] == 7 - (int8_t)index);
  }
}

static void test_q8_0_decode(void) {
  qbs_block_q8_0_t block = {.d = UINT16_C(0x3c00)};
  int8_t expected[QBS_Q8_0_WEIGHT_BLOCK_ELEMENTS];
  for (unsigned index = 0; index < QBS_Q8_0_WEIGHT_BLOCK_ELEMENTS; ++index) {
    expected[index] = (int8_t)((int)index - 16);
    block.qs[index] = expected[index];
  }
  int8_t actual[QBS_Q8_0_WEIGHT_BLOCK_ELEMENTS];
  qbs_ref_decode_q8_0(&block, actual);
  CHECK(memcmp(actual, expected, sizeof(actual)) == 0);
}

static void fill_q4_one(qbs_block_q4_k_t *block) {
  memset(block, 0, sizeof(*block));
  block->d = UINT16_C(0x3c00);
  block->dmin = UINT16_C(0x3800);
  for (unsigned index = 0; index < 8; ++index) block->scales[index] = 1;
  for (unsigned index = 8; index < 12; ++index) block->scales[index] = 0x11;
  memset(block->qs, 0x11, sizeof(block->qs));
}

static void fill_q5_one(qbs_block_q5_k_t *block) {
  memset(block, 0, sizeof(*block));
  block->d = UINT16_C(0x3c00);
  block->dmin = UINT16_C(0x3800);
  for (unsigned index = 0; index < 8; ++index) block->scales[index] = 1;
  for (unsigned index = 8; index < 12; ++index) block->scales[index] = 0x11;
  memset(block->qs, 0x11, sizeof(block->qs));
}

static void fill_q6_one(qbs_block_q6_k_t *block) {
  memset(block, 0, sizeof(*block));
  memset(block->ql, 0x11, sizeof(block->ql));
  memset(block->qh, 0xaa, sizeof(block->qh));
  memset(block->scales, 1, sizeof(block->scales));
  block->d = UINT16_C(0x3c00);
}

static void fill_q3_one(qbs_block_q3_k_t *block) {
  memset(block, 0, sizeof(*block));
  memset(block->hmask, 0xff, sizeof(block->hmask));
  memset(block->qs, 0x55, sizeof(block->qs));
  for (unsigned group = 0; group < 16; ++group)
    set_q3_scale(block, group, 1);
  block->d = UINT16_C(0x3c00);
}

static void fill_activations(qbs_block_q8_k_t *blocks, unsigned k_blocks) {
  for (unsigned context = 0; context < 4; ++context) {
    for (unsigned block = 0; block < k_blocks; ++block) {
      qbs_block_q8_k_t *item = &blocks[context * k_blocks + block];
      item->d = 1.0f;
      memset(item->qs, (int)(context + 1u), sizeof(item->qs));
      for (unsigned subgroup = 0; subgroup < 16; ++subgroup)
        item->bsums[subgroup] = (int16_t)(16u * (context + 1u));
    }
  }
}

static void test_profile_execution(unsigned profile) {
  enum { kN = 5, kBlocks = 2, kElements = 32 };
  const size_t block_bytes = qbs_weight_block_bytes(profile);
  uint8_t row_weights[kN * kBlocks * sizeof(qbs_block_q6_k_t)];
  memset(row_weights, 0, sizeof(row_weights));
  for (unsigned row = 0; row < kN; ++row) {
    for (unsigned block = 0; block < kBlocks; ++block) {
      uint8_t *address = row_weights + (row * kBlocks + block) * block_bytes;
      if (profile == QBS_WEIGHT_PROFILE_Q4_K) {
        fill_q4_one((qbs_block_q4_k_t *)(void *)address);
      } else if (profile == QBS_WEIGHT_PROFILE_Q5_K) {
        fill_q5_one((qbs_block_q5_k_t *)(void *)address);
      } else if (profile == QBS_WEIGHT_PROFILE_Q3_K) {
        fill_q3_one((qbs_block_q3_k_t *)(void *)address);
      } else {
        fill_q6_one((qbs_block_q6_k_t *)(void *)address);
      }
    }
  }

  const size_t r4_bytes = qbs_ref_weight_storage_bytes(
      profile, QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR, kN, kBlocks);
  uint8_t *r4_weights = malloc(r4_bytes);
  CHECK(r4_weights != NULL);
  if (r4_weights == NULL) return;
  CHECK_STATUS(qbs_ref_repack_weight_r4(
                   profile, row_weights, kN * kBlocks * block_bytes, kN,
                   kBlocks, r4_weights, r4_bytes),
               QBS_REF_OK);

  qbs_block_q8_k_t activations[4 * kBlocks];
  qbs_block_q8_kx4_t interleaved[kBlocks];
  fill_activations(activations, kBlocks);
  CHECK_STATUS(qbs_ref_pack_activation_m4(activations, 4 * kBlocks, kBlocks,
                                          interleaved, kBlocks),
               QBS_REF_OK);

  for (unsigned m = 1; m <= 4; ++m) {
    const unsigned vd = m == 1 ? 3 : (m == 2 ? 2 : 4);
    float row_result[4 * kElements];
    float r4_result[4 * kElements];
    for (unsigned index = 0; index < 4 * kElements; ++index) {
      row_result[index] = 12345.0f;
      r4_result[index] = 12345.0f;
    }
    qbs_descriptor_v1_t descriptor = make_descriptor(
        profile, QBS_ACTIVATION_PROFILE_Q8_K,
        QBS_WEIGHT_LAYOUT_ROW_MAJOR, QBS_ACTIVATION_LAYOUT_ROW_MAJOR, kN,
        kBlocks);
    qbs_ref_result_t result = {0};
    trace_counts_t trace = {0};
    CHECK_STATUS(qbs_ref_execute(
                     &descriptor, m, vd, 1024, UINT64_C(0x2000), row_weights,
                     kN * kBlocks * block_bytes, activations,
                     m * kBlocks * sizeof(qbs_block_q8_k_t), row_result,
                     4 * kElements, count_trace, &trace, &result),
                 QBS_REF_OK);
    CHECK(result.destination_registers == (m == 1 ? 1u : (m == 2 ? 2u : 4u)));
    CHECK(result.destination_elements_per_register == kElements);
    CHECK(result.active_outputs == m * kN);
    CHECK(result.fflags == 0);
    const unsigned groups = qbs_weight_subgroup_count(profile);
    CHECK(trace.groups == m * kN * kBlocks * groups);
    CHECK(trace.blocks == m * kN * kBlocks);

    const float base = qbs_weight_correction_mode(profile) ==
                               QBS_CORRECTION_AFFINE_MIN
                           ? 256.0f
                           : 512.0f;
    for (unsigned context = 0; context < m; ++context) {
      for (unsigned output = 0; output < kN; ++output)
        CHECK(row_result[context * kElements + output] ==
              base * (float)(context + 1u));
      for (unsigned output = kN; output < kElements; ++output)
        CHECK(float_bits(row_result[context * kElements + output]) == 0);
    }
    if (m == 3) {
      for (unsigned output = 0; output < kElements; ++output)
        CHECK(row_result[3 * kElements + output] == 12345.0f);
    }

    descriptor = make_descriptor(
        profile, QBS_ACTIVATION_PROFILE_Q8_K,
        QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
        m == 4 ? QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED
               : QBS_ACTIVATION_LAYOUT_ROW_MAJOR,
        kN, kBlocks);
    const void *activation_data = m == 4 ? (const void *)interleaved
                                         : (const void *)activations;
    const size_t activation_bytes =
        m == 4 ? sizeof(interleaved)
               : m * kBlocks * sizeof(qbs_block_q8_k_t);
    CHECK_STATUS(qbs_ref_execute(
                     &descriptor, m, vd, 1024, UINT64_C(0x2000), r4_weights,
                     r4_bytes, activation_data, activation_bytes, r4_result,
                     4 * kElements, NULL, NULL, &result),
                 QBS_REF_OK);
    const unsigned written_elements = m * kElements;
    CHECK(memcmp(row_result, r4_result,
                 written_elements * sizeof(float)) == 0);
  }

  float destination[32];
  for (unsigned index = 0; index < 32; ++index) destination[index] = 77.0f;
  const float original[32] = {
      77.0f, 77.0f, 77.0f, 77.0f, 77.0f, 77.0f, 77.0f, 77.0f,
      77.0f, 77.0f, 77.0f, 77.0f, 77.0f, 77.0f, 77.0f, 77.0f,
      77.0f, 77.0f, 77.0f, 77.0f, 77.0f, 77.0f, 77.0f, 77.0f,
      77.0f, 77.0f, 77.0f, 77.0f, 77.0f, 77.0f, 77.0f, 77.0f,
  };
  qbs_descriptor_v1_t descriptor = make_descriptor(
      profile, QBS_ACTIVATION_PROFILE_Q8_K, QBS_WEIGHT_LAYOUT_ROW_MAJOR,
      QBS_ACTIVATION_LAYOUT_ROW_MAJOR, kN, kBlocks);
  qbs_ref_result_t result = {0};
  CHECK_STATUS(qbs_ref_execute(
                   &descriptor, 1, 0, 1024, UINT64_C(0x2000), row_weights,
                   block_bytes, activations, sizeof(activations), destination,
                   32, NULL, NULL, &result),
               QBS_REF_BUFFER_SIZE);
  CHECK(memcmp(destination, original, sizeof(destination)) == 0);
  free(r4_weights);
}

static void test_q8_0_activation_execution(unsigned weight_profile) {
  enum { kN = 5, kBlocks = 2, kElements = 32 };
  const size_t block_bytes = qbs_weight_block_bytes(weight_profile);
  _Alignas(qbs_block_q8_0_t)
      uint8_t row_weights[kN * kBlocks * sizeof(qbs_block_q8_0_t)];
  memset(row_weights, 0, sizeof(row_weights));
  qbs_block_q8_0_t activations[4 * kBlocks];
  for (unsigned row = 0; row < kN; ++row) {
    for (unsigned block = 0; block < kBlocks; ++block) {
      uint8_t *address = row_weights +
          ((size_t)row * kBlocks + block) * block_bytes;
      if (weight_profile == QBS_WEIGHT_PROFILE_Q4_0) {
        qbs_block_q4_0_t *weight = (qbs_block_q4_0_t *)(void *)address;
        weight->d = UINT16_C(0x3c00);
        memset(weight->qs, 0x99, sizeof(weight->qs));
      } else {
        qbs_block_q8_0_t *weight = (qbs_block_q8_0_t *)(void *)address;
        weight->d = UINT16_C(0x3c00);
        memset(weight->qs, 1, sizeof(weight->qs));
      }
    }
  }
  for (unsigned context = 0; context < 4; ++context) {
    for (unsigned block = 0; block < kBlocks; ++block) {
      qbs_block_q8_0_t *activation =
          &activations[context * kBlocks + block];
      activation->d = UINT16_C(0x3c00);
      memset(activation->qs, (int)(context + 1u), sizeof(activation->qs));
    }
  }

  const size_t r4_bytes = qbs_ref_weight_storage_bytes(
      weight_profile, QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR, kN, kBlocks);
  uint8_t *r4_weights = malloc(r4_bytes);
  CHECK(r4_weights != NULL);
  if (r4_weights == NULL) return;
  CHECK_STATUS(qbs_ref_repack_weight_r4(
                   weight_profile, row_weights,
                   kN * kBlocks * block_bytes, kN, kBlocks, r4_weights,
                   r4_bytes),
               QBS_REF_OK);

  qbs_block_q8_0x4_t interleaved[kBlocks];
  CHECK_STATUS(qbs_ref_pack_activation_m4_profile(
                   QBS_ACTIVATION_PROFILE_Q8_0, activations,
                   sizeof(activations), kBlocks, interleaved,
                   sizeof(interleaved)),
               QBS_REF_OK);

  for (unsigned m = 1; m <= 4; ++m) {
    const unsigned vd = m == 1 ? 3 : (m == 2 ? 2 : 4);
    float row_result[4 * kElements];
    float packed_result[4 * kElements];
    for (unsigned index = 0; index < 4 * kElements; ++index) {
      row_result[index] = 12345.0f;
      packed_result[index] = 12345.0f;
    }
    qbs_descriptor_v1_t descriptor = make_descriptor(
        weight_profile, QBS_ACTIVATION_PROFILE_Q8_0,
        QBS_WEIGHT_LAYOUT_ROW_MAJOR, QBS_ACTIVATION_LAYOUT_ROW_MAJOR, kN,
        kBlocks);
    qbs_ref_result_t result = {0};
    trace_counts_t trace = {0};
    CHECK_STATUS(qbs_ref_execute(
                     &descriptor, m, vd, 1024, UINT64_C(0x2000), row_weights,
                     kN * kBlocks * block_bytes, activations,
                     m * kBlocks * sizeof(qbs_block_q8_0_t), row_result,
                     4 * kElements, count_trace, &trace, &result),
                 QBS_REF_OK);
    CHECK(trace.groups == m * kN * kBlocks);
    CHECK(trace.blocks == m * kN * kBlocks);
    for (unsigned context = 0; context < m; ++context) {
      for (unsigned output = 0; output < kN; ++output)
        CHECK(row_result[context * kElements + output] ==
              64.0f * (float)(context + 1u));
      for (unsigned output = kN; output < kElements; ++output)
        CHECK(float_bits(row_result[context * kElements + output]) == 0);
    }

    descriptor = make_descriptor(
        weight_profile, QBS_ACTIVATION_PROFILE_Q8_0,
        QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
        m == 4 ? QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED
               : QBS_ACTIVATION_LAYOUT_ROW_MAJOR,
        kN, kBlocks);
    const void *activation_data =
        m == 4 ? (const void *)interleaved : (const void *)activations;
    const size_t activation_bytes = m == 4
        ? sizeof(interleaved)
        : m * kBlocks * sizeof(qbs_block_q8_0_t);
    CHECK_STATUS(qbs_ref_execute(
                     &descriptor, m, vd, 1024, UINT64_C(0x2000), r4_weights,
                     r4_bytes, activation_data, activation_bytes,
                     packed_result, 4 * kElements, NULL, NULL, &result),
                 QBS_REF_OK);
    CHECK(memcmp(row_result, packed_result,
                 m * kElements * sizeof(float)) == 0);
  }
  free(r4_weights);
}

int main(void) {
  test_abi();
  test_descriptor_validation();
  test_q8_quantization();
  test_q4_decode();
  test_q5_decode();
  test_q6_decode();
  test_q3_decode();
  test_q4_0_decode();
  test_q8_0_decode();
  test_profile_execution(QBS_WEIGHT_PROFILE_Q4_K);
  test_profile_execution(QBS_WEIGHT_PROFILE_Q5_K);
  test_profile_execution(QBS_WEIGHT_PROFILE_Q6_K);
  test_profile_execution(QBS_WEIGHT_PROFILE_Q3_K);
  test_q8_0_activation_execution(QBS_WEIGHT_PROFILE_Q4_0);
  test_q8_0_activation_execution(QBS_WEIGHT_PROFILE_Q8_0_WEIGHT);
  if (failures != 0) {
    fprintf(stderr, "qbs_ref_test: %u failure(s)\n", failures);
    return EXIT_FAILURE;
  }
  puts("qbs_ref_test: PASS");
  return EXIT_SUCCESS;
}
