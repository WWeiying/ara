#include "qbs_ref.h"

#include <inttypes.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { PATTERN_ZERO = 0, PATTERN_EDGE = 1, PATTERN_RANDOM = 2 };

typedef union {
  qbs_block_q4_k_t q4[4];
  qbs_block_q5_k_t q5[4];
  qbs_block_q6_k_t q6[4];
  qbs_block_q3_k_t q3[4];
  qbs_block_q8_0_t q8_0_weight[4];
  qbs_block_q4_0_t q4_0[4];
  qbs_block_q2_k_t q2[4];
  qbs_block_q5_0_t q5_0[4];
  qbs_block_iq4_nl_t iq4_nl[4];
  uint8_t bytes[4 * QBS_MAX_WEIGHT_BLOCK_BYTES];
} weight_storage_t;

typedef union {
  qbs_block_q8_k_t q8_k[4];
  qbs_block_q8_0_t q8_0[4];
  uint8_t bytes[4 * QBS_MAX_ACTIVATION_BLOCK_BYTES];
} activation_storage_t;

typedef struct {
  bool valid;
  int32_t dot;
  int32_t aux;
  int16_t scale;
  int16_t min;
} group_expected_t;

typedef struct {
  group_expected_t group[16][16];
  int32_t result_dot[16];
  int32_t result_aux[16];
  uint32_t result_fp_bits[16];
  bool result_valid[16];
} trace_expected_t;

static uint32_t random_state = UINT32_C(0x61726151);

static uint32_t next_random(void) {
  random_state = random_state * UINT32_C(1664525) + UINT32_C(1013904223);
  return random_state;
}

static void record_trace(const qbs_trace_event_t *event, void *opaque) {
  trace_expected_t *expected = opaque;
  const unsigned stream = event->output * 4u + event->context;
  if (event->kind == QBS_TRACE_GROUP) {
    group_expected_t *group = &expected->group[stream][event->group];
    group->valid = true;
    group->dot = event->group_dot;
    group->aux = event->group_aux;
    group->scale = event->group_scale;
    group->min = event->group_min;
  } else {
    expected->result_valid[stream] = true;
    expected->result_dot[stream] = event->block_dot;
    expected->result_aux[stream] = event->block_aux;
    memcpy(&expected->result_fp_bits[stream], &event->accumulator_after,
           sizeof(expected->result_fp_bits[stream]));
  }
}

static void set_activation_pattern(qbs_block_q8_k_t *block, unsigned pattern,
                                   unsigned ctx, unsigned case_id) {
  uint32_t d_bits = UINT32_C(0x3f000000) + (ctx << 18) + (case_id << 5);
  memcpy(&block->d, &d_bits, sizeof(d_bits));
  for (unsigned element = 0; element < QBS_BLOCK_ELEMENTS; ++element) {
    int value = 0;
    if (pattern == PATTERN_EDGE) {
      value = (element & 1u) != 0 ? 127 : -128;
    } else if (pattern == PATTERN_RANDOM) {
      value = (int)(next_random() & 0xffu) - 128;
    }
    block->qs[element] = (int8_t)value;
  }
  for (unsigned subgroup = 0; subgroup < 16; ++subgroup) {
    int sum = 0;
    for (unsigned item = 0; item < 16; ++item)
      sum += block->qs[subgroup * 16u + item];
    block->bsums[subgroup] = (int16_t)sum;
  }
}

static void set_q8_0_pattern(qbs_block_q8_0_t *block, unsigned pattern,
                             unsigned ctx, unsigned case_id) {
  block->d = (qbs_fp16_t)(UINT16_C(0x3400) + ctx * 0x40u + case_id);
  for (unsigned element = 0; element < QBS_Q8_0_BLOCK_ELEMENTS; ++element) {
    int value = 0;
    if (pattern == PATTERN_EDGE) {
      value = (element & 1u) != 0 ? 127 : -128;
    } else if (pattern == PATTERN_RANDOM) {
      value = (int)(next_random() & 0xffu) - 128;
    }
    block->qs[element] = (int8_t)value;
  }
}

static void set_q4_pattern(qbs_block_q4_k_t *block, unsigned pattern,
                           unsigned row, unsigned case_id) {
  block->d = (qbs_fp16_t)(UINT16_C(0x3400) + row * 0x40u + case_id);
  block->dmin =
      (qbs_fp16_t)(UINT16_C(0x3000) + row * 0x20u + case_id);
  for (unsigned i = 0; i < sizeof(block->scales); ++i) {
    if (pattern == PATTERN_ZERO)
      block->scales[i] = 0;
    else if (pattern == PATTERN_EDGE)
      block->scales[i] = 0xffu;
    else
      block->scales[i] = (uint8_t)next_random();
  }
  for (unsigned i = 0; i < sizeof(block->qs); ++i) {
    if (pattern == PATTERN_ZERO)
      block->qs[i] = 0;
    else if (pattern == PATTERN_EDGE)
      block->qs[i] = (i & 1u) != 0 ? 0xf0u : 0x0fu;
    else
      block->qs[i] = (uint8_t)next_random();
  }
}

static void set_q5_pattern(qbs_block_q5_k_t *block, unsigned pattern,
                           unsigned row, unsigned case_id) {
  block->d = (qbs_fp16_t)(UINT16_C(0x3400) + row * 0x40u + case_id);
  block->dmin =
      (qbs_fp16_t)(UINT16_C(0x3000) + row * 0x20u + case_id);
  for (unsigned i = 0; i < sizeof(block->scales); ++i) {
    if (pattern == PATTERN_ZERO)
      block->scales[i] = 0;
    else if (pattern == PATTERN_EDGE)
      block->scales[i] = 0xffu;
    else
      block->scales[i] = (uint8_t)next_random();
  }
  for (unsigned i = 0; i < sizeof(block->qh); ++i) {
    if (pattern == PATTERN_ZERO)
      block->qh[i] = 0;
    else if (pattern == PATTERN_EDGE)
      block->qh[i] = (i & 1u) != 0 ? 0xffu : 0;
    else
      block->qh[i] = (uint8_t)next_random();
  }
  for (unsigned i = 0; i < sizeof(block->qs); ++i) {
    if (pattern == PATTERN_ZERO)
      block->qs[i] = 0;
    else if (pattern == PATTERN_EDGE)
      block->qs[i] = (i & 1u) != 0 ? 0xf0u : 0x0fu;
    else
      block->qs[i] = (uint8_t)next_random();
  }
}

static void set_q6_pattern(qbs_block_q6_k_t *block, unsigned pattern,
                           unsigned row, unsigned case_id) {
  block->d = (qbs_fp16_t)(UINT16_C(0x3800) + row * 0x40u + case_id);
  for (unsigned i = 0; i < sizeof(block->ql); ++i) {
    if (pattern == PATTERN_ZERO)
      block->ql[i] = 0;
    else if (pattern == PATTERN_EDGE)
      block->ql[i] = (i & 1u) != 0 ? 0xffu : 0;
    else
      block->ql[i] = (uint8_t)next_random();
  }
  for (unsigned i = 0; i < sizeof(block->qh); ++i) {
    if (pattern == PATTERN_ZERO)
      block->qh[i] = 0xaau;
    else if (pattern == PATTERN_EDGE)
      block->qh[i] = (i & 1u) != 0 ? 0xffu : 0;
    else
      block->qh[i] = (uint8_t)next_random();
  }
  for (unsigned i = 0; i < sizeof(block->scales); ++i) {
    if (pattern == PATTERN_ZERO)
      block->scales[i] = 0;
    else if (pattern == PATTERN_EDGE)
      block->scales[i] = (i & 1u) != 0 ? 127 : -128;
    else
      block->scales[i] = (int8_t)next_random();
  }
}

static void set_q3_pattern(qbs_block_q3_k_t *block, unsigned pattern,
                           unsigned row, unsigned case_id) {
  block->d = (qbs_fp16_t)(UINT16_C(0x3800) + row * 0x40u + case_id);
  for (unsigned i = 0; i < sizeof(block->hmask); ++i) {
    if (pattern == PATTERN_ZERO)
      block->hmask[i] = 0xffu;
    else if (pattern == PATTERN_EDGE)
      block->hmask[i] = (i & 1u) != 0 ? 0xffu : 0;
    else
      block->hmask[i] = (uint8_t)next_random();
  }
  for (unsigned i = 0; i < sizeof(block->qs); ++i) {
    if (pattern == PATTERN_ZERO)
      block->qs[i] = 0;
    else if (pattern == PATTERN_EDGE)
      block->qs[i] = (i & 1u) != 0 ? 0xffu : 0;
    else
      block->qs[i] = (uint8_t)next_random();
  }
  for (unsigned i = 0; i < sizeof(block->scales); ++i) {
    if (pattern == PATTERN_ZERO)
      block->scales[i] = i >= 8u ? 0xaau : 0;
    else if (pattern == PATTERN_EDGE)
      block->scales[i] = 0xffu;
    else
      block->scales[i] = (uint8_t)next_random();
  }
}

static void set_q4_0_pattern(qbs_block_q4_0_t *block, unsigned pattern,
                             unsigned row, unsigned case_id) {
  block->d = (qbs_fp16_t)(UINT16_C(0x3800) + row * 0x40u + case_id);
  for (unsigned i = 0; i < sizeof(block->qs); ++i) {
    if (pattern == PATTERN_ZERO)
      block->qs[i] = 0x88u;
    else if (pattern == PATTERN_EDGE)
      block->qs[i] = (i & 1u) != 0 ? 0xf0u : 0x0fu;
    else
      block->qs[i] = (uint8_t)next_random();
  }
}

static void set_q8_0_weight_pattern(qbs_block_q8_0_t *block,
                                    unsigned pattern, unsigned row,
                                    unsigned case_id) {
  block->d = (qbs_fp16_t)(UINT16_C(0x3800) + row * 0x40u + case_id);
  for (unsigned i = 0; i < sizeof(block->qs); ++i) {
    if (pattern == PATTERN_ZERO)
      block->qs[i] = 0;
    else if (pattern == PATTERN_EDGE)
      block->qs[i] = (i & 1u) != 0 ? 127 : -128;
    else
      block->qs[i] = (int8_t)next_random();
  }
}

static void set_q2_pattern(qbs_block_q2_k_t *block, unsigned pattern,
                           unsigned row, unsigned case_id) {
  block->d = (qbs_fp16_t)(UINT16_C(0x3400) + row * 0x40u + case_id);
  block->dmin =
      (qbs_fp16_t)(UINT16_C(0x3000) + row * 0x20u + case_id);
  for (unsigned i = 0; i < sizeof(block->scales); ++i) {
    if (pattern == PATTERN_ZERO)
      block->scales[i] = 0;
    else if (pattern == PATTERN_EDGE)
      block->scales[i] = 0xffu;
    else
      block->scales[i] = (uint8_t)next_random();
  }
  for (unsigned i = 0; i < sizeof(block->qs); ++i) {
    if (pattern == PATTERN_ZERO)
      block->qs[i] = 0;
    else if (pattern == PATTERN_EDGE)
      block->qs[i] = (i & 1u) != 0 ? 0xffu : 0;
    else
      block->qs[i] = (uint8_t)next_random();
  }
}

static void set_q5_0_pattern(qbs_block_q5_0_t *block, unsigned pattern,
                             unsigned row, unsigned case_id) {
  block->d = (qbs_fp16_t)(UINT16_C(0x3800) + row * 0x40u + case_id);
  for (unsigned i = 0; i < sizeof(block->qh); ++i) {
    if (pattern == PATTERN_ZERO)
      block->qh[i] = 0xffu;
    else if (pattern == PATTERN_EDGE)
      block->qh[i] = (i & 1u) != 0 ? 0xffu : 0;
    else
      block->qh[i] = (uint8_t)next_random();
  }
  for (unsigned i = 0; i < sizeof(block->qs); ++i) {
    if (pattern == PATTERN_ZERO)
      block->qs[i] = 0;
    else if (pattern == PATTERN_EDGE)
      block->qs[i] = (i & 1u) != 0 ? 0xffu : 0;
    else
      block->qs[i] = (uint8_t)next_random();
  }
}

static void set_iq4_nl_pattern(qbs_block_iq4_nl_t *block,
                               unsigned pattern, unsigned row,
                               unsigned case_id) {
  block->d = pattern == PATTERN_ZERO
                 ? 0
                 : (qbs_fp16_t)(UINT16_C(0x3800) + row * 0x40u + case_id);
  for (unsigned i = 0; i < sizeof(block->qs); ++i) {
    if (pattern == PATTERN_ZERO)
      block->qs[i] = 0x88u;
    else if (pattern == PATTERN_EDGE)
      block->qs[i] = (i & 1u) != 0 ? 0xf0u : 0x0fu;
    else
      block->qs[i] = (uint8_t)next_random();
  }
}

static unsigned activation_profile_for_weight(unsigned profile) {
  return qbs_default_activation_profile(profile);
}

static uint8_t *weight_block(weight_storage_t *storage, unsigned profile,
                             unsigned row) {
  switch (profile) {
    case QBS_WEIGHT_PROFILE_Q4_K:
      return (uint8_t *)&storage->q4[row];
    case QBS_WEIGHT_PROFILE_Q5_K:
      return (uint8_t *)&storage->q5[row];
    case QBS_WEIGHT_PROFILE_Q6_K:
      return (uint8_t *)&storage->q6[row];
    case QBS_WEIGHT_PROFILE_Q3_K:
      return (uint8_t *)&storage->q3[row];
    case QBS_WEIGHT_PROFILE_Q8_0_WEIGHT:
      return (uint8_t *)&storage->q8_0_weight[row];
    case QBS_WEIGHT_PROFILE_Q4_0:
      return (uint8_t *)&storage->q4_0[row];
    case QBS_WEIGHT_PROFILE_Q2_K:
      return (uint8_t *)&storage->q2[row];
    case QBS_WEIGHT_PROFILE_Q5_0:
      return (uint8_t *)&storage->q5_0[row];
    case QBS_WEIGHT_PROFILE_IQ4_NL:
      return (uint8_t *)&storage->iq4_nl[row];
    default:
      return NULL;
  }
}

static unsigned weight_scale(const weight_storage_t *storage,
                             unsigned profile, unsigned row) {
  switch (profile) {
    case QBS_WEIGHT_PROFILE_Q4_K: return storage->q4[row].d;
    case QBS_WEIGHT_PROFILE_Q5_K: return storage->q5[row].d;
    case QBS_WEIGHT_PROFILE_Q6_K: return storage->q6[row].d;
    case QBS_WEIGHT_PROFILE_Q3_K: return storage->q3[row].d;
    case QBS_WEIGHT_PROFILE_Q8_0_WEIGHT:
      return storage->q8_0_weight[row].d;
    case QBS_WEIGHT_PROFILE_Q4_0: return storage->q4_0[row].d;
    case QBS_WEIGHT_PROFILE_Q2_K: return storage->q2[row].d;
    case QBS_WEIGHT_PROFILE_Q5_0: return storage->q5_0[row].d;
    case QBS_WEIGHT_PROFILE_IQ4_NL: return storage->iq4_nl[row].d;
    default: return 0;
  }
}

static unsigned weight_min_scale(const weight_storage_t *storage,
                                 unsigned profile, unsigned row) {
  switch (profile) {
    case QBS_WEIGHT_PROFILE_Q4_K: return storage->q4[row].dmin;
    case QBS_WEIGHT_PROFILE_Q5_K: return storage->q5[row].dmin;
    case QBS_WEIGHT_PROFILE_Q2_K: return storage->q2[row].dmin;
    default: return 0;
  }
}

static uint8_t *activation_block(activation_storage_t *storage,
                                 unsigned profile, unsigned context) {
  switch (profile) {
    case QBS_ACTIVATION_PROFILE_Q8_K:
      return (uint8_t *)&storage->q8_k[context];
    case QBS_ACTIVATION_PROFILE_Q8_0:
      return (uint8_t *)&storage->q8_0[context];
    default:
      return NULL;
  }
}

static void print_beat(FILE *output, const char *role, unsigned bank,
                       unsigned offset, const uint8_t *data,
                       unsigned total_bytes) {
  uint16_t strobe = 0;
  uint8_t bytes[16] = {0};
  for (unsigned byte = 0; byte < 16; ++byte) {
    if (offset + byte < total_bytes) {
      bytes[byte] = data[offset + byte];
      strobe |= (uint16_t)(1u << byte);
    }
  }
  fprintf(output, "%s %u %u %04x ", role, bank, offset, strobe);
  for (int byte = 15; byte >= 0; --byte) fprintf(output, "%02x", bytes[byte]);
  fputc('\n', output);
}

static int emit_case(FILE *output, unsigned case_id, unsigned profile,
                     unsigned m, unsigned rows, unsigned pattern) {
  weight_storage_t weights;
  activation_storage_t activations;
  uint8_t repeated_weights[4 * 2 * QBS_MAX_WEIGHT_BLOCK_BYTES];
  uint8_t repeated_activations[4 * 2 * QBS_MAX_ACTIVATION_BLOCK_BYTES];
  int8_t decoded_weight[4][256];
  int8_t decoded_activation[4][256];
  uint8_t unsigned_scales[16];
  uint8_t unsigned_mins[16];
  int8_t q6_scales[16];
  trace_expected_t expected;
  trace_expected_t repeated_expected;
  float destination[128];
  float repeated_destination[128];
  qbs_ref_result_t result;
  qbs_ref_result_t repeated_result;
  memset(&weights, 0, sizeof(weights));
  memset(&activations, 0, sizeof(activations));
  memset(repeated_weights, 0, sizeof(repeated_weights));
  memset(repeated_activations, 0, sizeof(repeated_activations));
  memset(&expected, 0, sizeof(expected));
  memset(&repeated_expected, 0, sizeof(repeated_expected));
  memset(destination, 0, sizeof(destination));
  memset(repeated_destination, 0, sizeof(repeated_destination));

  for (unsigned row = 0; row < rows; ++row) {
    if (profile == QBS_WEIGHT_PROFILE_Q4_K) {
      set_q4_pattern(&weights.q4[row], pattern, row, case_id);
      qbs_ref_decode_q4_k(&weights.q4[row], decoded_weight[row],
                          unsigned_scales, unsigned_mins);
    } else if (profile == QBS_WEIGHT_PROFILE_Q5_K) {
      set_q5_pattern(&weights.q5[row], pattern, row, case_id);
      qbs_ref_decode_q5_k(&weights.q5[row], decoded_weight[row],
                          unsigned_scales, unsigned_mins);
    } else if (profile == QBS_WEIGHT_PROFILE_Q6_K) {
      set_q6_pattern(&weights.q6[row], pattern, row, case_id);
      qbs_ref_decode_q6_k(&weights.q6[row], decoded_weight[row], q6_scales);
    } else if (profile == QBS_WEIGHT_PROFILE_Q3_K) {
      set_q3_pattern(&weights.q3[row], pattern, row, case_id);
      qbs_ref_decode_q3_k(&weights.q3[row], decoded_weight[row], q6_scales);
    } else if (profile == QBS_WEIGHT_PROFILE_Q8_0_WEIGHT) {
      set_q8_0_weight_pattern(&weights.q8_0_weight[row], pattern, row,
                              case_id);
      qbs_ref_decode_q8_0(&weights.q8_0_weight[row], decoded_weight[row]);
    } else if (profile == QBS_WEIGHT_PROFILE_Q4_0) {
      set_q4_0_pattern(&weights.q4_0[row], pattern, row, case_id);
      qbs_ref_decode_q4_0(&weights.q4_0[row], decoded_weight[row]);
    } else if (profile == QBS_WEIGHT_PROFILE_Q2_K) {
      set_q2_pattern(&weights.q2[row], pattern, row, case_id);
      qbs_ref_decode_q2_k(&weights.q2[row], decoded_weight[row],
                          unsigned_scales, unsigned_mins);
    } else if (profile == QBS_WEIGHT_PROFILE_Q5_0) {
      set_q5_0_pattern(&weights.q5_0[row], pattern, row, case_id);
      qbs_ref_decode_q5_0(&weights.q5_0[row], decoded_weight[row]);
    } else if (profile == QBS_WEIGHT_PROFILE_IQ4_NL) {
      set_iq4_nl_pattern(&weights.iq4_nl[row], pattern, row, case_id);
      qbs_ref_decode_iq4_nl(&weights.iq4_nl[row], decoded_weight[row]);
    } else {
      return 1;
    }
  }
  const unsigned activation_profile = activation_profile_for_weight(profile);
  const size_t activation_block_bytes =
      qbs_activation_block_bytes(activation_profile);
  for (unsigned ctx = 0; ctx < m; ++ctx) {
    if (activation_profile == QBS_ACTIVATION_PROFILE_Q8_K) {
      set_activation_pattern(&activations.q8_k[ctx], pattern, ctx, case_id);
      memcpy(decoded_activation[ctx], activations.q8_k[ctx].qs,
             QBS_Q8_K_BLOCK_ELEMENTS);
    } else {
      set_q8_0_pattern(&activations.q8_0[ctx], pattern, ctx, case_id);
      memcpy(decoded_activation[ctx], activations.q8_0[ctx].qs,
             QBS_Q8_0_BLOCK_ELEMENTS);
    }
  }

  const qbs_descriptor_fields_t fields = {
      .descriptor_version = QBS_DESCRIPTOR_VERSION,
      .weight_profile = (uint8_t)profile,
      .activation_profile = (uint8_t)activation_profile,
      .weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR,
      .activation_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR,
      .n = (uint8_t)rows,
      .k_blocks = 1,
  };
  qbs_descriptor_t descriptor __attribute__((aligned(16))) = {
      .header = qbs_pack_descriptor_header(&fields),
      .weight_base = (uintptr_t)&weights,
  };
  const size_t block_bytes = qbs_weight_block_bytes(profile);
  const unsigned block_elements = qbs_weight_block_elements(profile);
  const qbs_ref_status_t status = qbs_ref_execute(
      &descriptor, m, 0, 1024, (uintptr_t)&activations, &weights,
      rows * block_bytes, &activations, m * activation_block_bytes,
      destination, sizeof(destination) / sizeof(destination[0]), record_trace,
      &expected, &result);
  if (status != QBS_REF_OK) {
    fprintf(stderr, "reference case %u failed: %s\n", case_id,
            qbs_ref_status_string(status));
    return 1;
  }

  for (unsigned row = 0; row < rows; ++row) {
    const uint8_t *block = weight_block(&weights, profile, row);
    for (unsigned repeat = 0; repeat < 2; ++repeat)
      memcpy(repeated_weights + (row * 2u + repeat) * block_bytes, block,
             block_bytes);
  }
  for (unsigned ctx = 0; ctx < m; ++ctx)
    for (unsigned repeat = 0; repeat < 2; ++repeat)
      memcpy(repeated_activations +
                 (ctx * 2u + repeat) * activation_block_bytes,
             activation_block(&activations, activation_profile, ctx),
             activation_block_bytes);

  qbs_descriptor_fields_t repeated_fields = fields;
  repeated_fields.k_blocks = 2;
  qbs_descriptor_t repeated_descriptor __attribute__((aligned(16))) = {
      .header = qbs_pack_descriptor_header(&repeated_fields),
      .weight_base = (uintptr_t)repeated_weights,
  };
  const qbs_ref_status_t repeated_status = qbs_ref_execute(
      &repeated_descriptor, m, 0, 1024, (uintptr_t)repeated_activations,
      repeated_weights, rows * 2u * block_bytes, repeated_activations,
      m * 2u * activation_block_bytes, repeated_destination,
      sizeof(repeated_destination) / sizeof(repeated_destination[0]),
      record_trace, &repeated_expected, &repeated_result);
  if (repeated_status != QBS_REF_OK) {
    fprintf(stderr, "repeated reference case %u failed: %s\n", case_id,
            qbs_ref_status_string(repeated_status));
    return 1;
  }

  fprintf(output, "CASE %u %u %u %u %u\n", case_id, profile, m, rows,
          pattern);
  for (unsigned row = 0; row < rows; ++row) {
    const uint8_t *block = weight_block(&weights, profile, row);
    for (unsigned offset = 0; offset < block_bytes; offset += 16)
      print_beat(output, "W", row, offset, block, (unsigned)block_bytes);
  }
  for (unsigned ctx = 0; ctx < m; ++ctx) {
    for (unsigned offset = 0; offset < activation_block_bytes; offset += 16)
      print_beat(output, "A", ctx, offset,
                 activation_block(&activations, activation_profile, ctx),
                 (unsigned)activation_block_bytes);
  }
  for (unsigned row = 0; row < rows; ++row) {
    fprintf(output, "QW %u", row);
    for (unsigned element = 0; element < block_elements; ++element)
      fprintf(output, " %d", decoded_weight[row][element]);
    fputc('\n', output);
  }
  for (unsigned ctx = 0; ctx < m; ++ctx) {
    fprintf(output, "QA %u", ctx);
    for (unsigned element = 0; element < block_elements; ++element)
      fprintf(output, " %d", decoded_activation[ctx][element]);
    fputc('\n', output);
  }

  const unsigned groups = qbs_weight_subgroup_count(profile);
  for (unsigned stream = 0; stream < 16; ++stream) {
    const unsigned row = stream / 4u;
    const unsigned ctx = stream % 4u;
    if (row >= rows || ctx >= m) continue;
    for (unsigned group = 0; group < groups; ++group) {
      const group_expected_t *entry = &expected.group[stream][group];
      if (!entry->valid) {
        fprintf(stderr, "missing group trace case=%u stream=%u group=%u\n",
                case_id, stream, group);
        return 1;
      }
      fprintf(output, "G %u %u %" PRId32 " %" PRId32 " %d %d\n",
              stream, group, entry->dot, entry->aux, entry->scale,
              entry->min);
    }
  }
  for (unsigned stream = 0; stream < 16; ++stream) {
    const unsigned row = stream / 4u;
    const unsigned ctx = stream % 4u;
    if (row >= rows || ctx >= m) continue;
    if (!expected.result_valid[stream]) {
      fprintf(stderr, "missing block trace case=%u stream=%u\n", case_id,
              stream);
      return 1;
    }
    const unsigned weight_d = weight_scale(&weights, profile, row);
    const unsigned weight_dmin = weight_min_scale(&weights, profile, row);
    uint32_t activation_d = 0;
    memcpy(&activation_d,
           activation_block(&activations, activation_profile, ctx),
           qbs_activation_scale_bytes(activation_profile));
    fprintf(output,
            "R %u %" PRId32 " %" PRId32 " %04x %04x %08" PRIx32
            " %08" PRIx32 " %08" PRIx32 "\n",
            stream, expected.result_dot[stream], expected.result_aux[stream],
            weight_d, weight_dmin, activation_d,
            expected.result_fp_bits[stream],
            repeated_expected.result_fp_bits[stream]);
  }

  const unsigned k_per = m == 1 ? 8 : (m == 2 ? 4 : 2);
  const unsigned cycles = block_elements / k_per;
  fprintf(output, "F %02" PRIx32 " %02" PRIx32 "\n", result.fflags,
          repeated_result.fflags);
  fprintf(output, "C %u %u %u\n", rows * m * block_elements,
          cycles * rows * 8u, cycles);
  fprintf(output, "END\n");
  return 0;
}

int main(int argc, char **argv) {
  if (argc != 2) {
    fprintf(stderr, "usage: %s OUTPUT\n", argv[0]);
    return 2;
  }
  FILE *output = fopen(argv[1], "w");
  if (output == NULL) {
    perror(argv[1]);
    return 2;
  }

  static const unsigned profiles[] = {QBS_WEIGHT_PROFILE_Q4_K,
                                      QBS_WEIGHT_PROFILE_Q5_K,
                                      QBS_WEIGHT_PROFILE_Q6_K,
                                      QBS_WEIGHT_PROFILE_Q3_K,
                                      QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
                                      QBS_WEIGHT_PROFILE_Q4_0,
                                      QBS_WEIGHT_PROFILE_Q2_K,
                                      QBS_WEIGHT_PROFILE_Q5_0,
                                      QBS_WEIGHT_PROFILE_IQ4_NL};
  const unsigned case_count =
      (unsigned)(sizeof(profiles) / sizeof(profiles[0])) * 4u * 4u * 3u;
  fprintf(output, "QBSV1 %u\n", case_count);
  unsigned case_id = 0;
  for (unsigned profile_index = 0;
       profile_index < sizeof(profiles) / sizeof(profiles[0]);
       ++profile_index) {
    const unsigned profile = profiles[profile_index];
    for (unsigned m = 1; m <= 4; ++m) {
      for (unsigned rows = 1; rows <= 4; ++rows) {
        for (unsigned pattern = PATTERN_ZERO; pattern <= PATTERN_RANDOM;
             ++pattern) {
          if (emit_case(output, case_id, profile, m, rows, pattern) != 0) {
            fclose(output);
            return 1;
          }
          ++case_id;
        }
      }
    }
  }
  fclose(output);
  printf("wrote %u QBS RTL cases to %s\n", case_id, argv[1]);
  return 0;
}
