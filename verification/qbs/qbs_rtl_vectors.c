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
  qbs_block_q6_k_t q6[4];
  uint8_t bytes[4 * QBS_Q6_K_BLOCK_BYTES];
} weight_storage_t;

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
  qbs_block_q8_k_t activations[4];
  uint8_t repeated_weights[4 * 2 * QBS_Q6_K_BLOCK_BYTES];
  qbs_block_q8_k_t repeated_activations[4 * 2];
  int8_t decoded_weight[4][256];
  int8_t decoded_activation[4][256];
  uint8_t q4_scales[8];
  uint8_t q4_mins[8];
  int8_t q6_scales[16];
  trace_expected_t expected;
  trace_expected_t repeated_expected;
  float destination[128];
  float repeated_destination[128];
  qbs_ref_result_t result;
  qbs_ref_result_t repeated_result;
  memset(&weights, 0, sizeof(weights));
  memset(activations, 0, sizeof(activations));
  memset(repeated_weights, 0, sizeof(repeated_weights));
  memset(repeated_activations, 0, sizeof(repeated_activations));
  memset(&expected, 0, sizeof(expected));
  memset(&repeated_expected, 0, sizeof(repeated_expected));
  memset(destination, 0, sizeof(destination));
  memset(repeated_destination, 0, sizeof(repeated_destination));

  for (unsigned row = 0; row < rows; ++row) {
    if (profile == QBS_WEIGHT_PROFILE_Q4_K) {
      set_q4_pattern(&weights.q4[row], pattern, row, case_id);
      qbs_ref_decode_q4_k(&weights.q4[row], decoded_weight[row], q4_scales,
                          q4_mins);
    } else {
      set_q6_pattern(&weights.q6[row], pattern, row, case_id);
      qbs_ref_decode_q6_k(&weights.q6[row], decoded_weight[row], q6_scales);
    }
  }
  for (unsigned ctx = 0; ctx < m; ++ctx) {
    set_activation_pattern(&activations[ctx], pattern, ctx, case_id);
    memcpy(decoded_activation[ctx], activations[ctx].qs,
           QBS_BLOCK_ELEMENTS);
  }

  const qbs_descriptor_fields_t fields = {
      .descriptor_version = QBS_DESCRIPTOR_VERSION,
      .weight_profile = (uint8_t)profile,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
      .weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR,
      .activation_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR,
      .n = (uint8_t)rows,
      .k_blocks = 1,
  };
  qbs_descriptor_v1_t descriptor __attribute__((aligned(16))) = {
      .header = qbs_pack_descriptor_header(&fields),
      .weight_base = (uintptr_t)&weights,
  };
  const size_t block_bytes = profile == QBS_WEIGHT_PROFILE_Q4_K
                                 ? QBS_Q4_K_BLOCK_BYTES
                                 : QBS_Q6_K_BLOCK_BYTES;
  const qbs_ref_status_t status = qbs_ref_execute(
      &descriptor, m, 0, 1024, (uintptr_t)activations, &weights,
      rows * block_bytes, activations, m * sizeof(activations[0]), destination,
      sizeof(destination) / sizeof(destination[0]), record_trace, &expected,
      &result);
  if (status != QBS_REF_OK) {
    fprintf(stderr, "reference case %u failed: %s\n", case_id,
            qbs_ref_status_string(status));
    return 1;
  }

  for (unsigned row = 0; row < rows; ++row) {
    const uint8_t *block = profile == QBS_WEIGHT_PROFILE_Q4_K
                               ? (const uint8_t *)&weights.q4[row]
                               : (const uint8_t *)&weights.q6[row];
    for (unsigned repeat = 0; repeat < 2; ++repeat)
      memcpy(repeated_weights + (row * 2u + repeat) * block_bytes, block,
             block_bytes);
  }
  for (unsigned ctx = 0; ctx < m; ++ctx)
    for (unsigned repeat = 0; repeat < 2; ++repeat)
      repeated_activations[ctx * 2u + repeat] = activations[ctx];

  qbs_descriptor_fields_t repeated_fields = fields;
  repeated_fields.k_blocks = 2;
  qbs_descriptor_v1_t repeated_descriptor __attribute__((aligned(16))) = {
      .header = qbs_pack_descriptor_header(&repeated_fields),
      .weight_base = (uintptr_t)repeated_weights,
  };
  const qbs_ref_status_t repeated_status = qbs_ref_execute(
      &repeated_descriptor, m, 0, 1024, (uintptr_t)repeated_activations,
      repeated_weights, rows * 2u * block_bytes, repeated_activations,
      m * 2u * sizeof(repeated_activations[0]), repeated_destination,
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
    const uint8_t *block = profile == QBS_WEIGHT_PROFILE_Q4_K
                               ? (const uint8_t *)&weights.q4[row]
                               : (const uint8_t *)&weights.q6[row];
    for (unsigned offset = 0; offset < block_bytes; offset += 16)
      print_beat(output, "W", row, offset, block, (unsigned)block_bytes);
  }
  for (unsigned ctx = 0; ctx < m; ++ctx) {
    for (unsigned offset = 0; offset < QBS_Q8_K_BLOCK_BYTES; offset += 16)
      print_beat(output, "A", ctx, offset,
                 (const uint8_t *)&activations[ctx], QBS_Q8_K_BLOCK_BYTES);
  }
  for (unsigned row = 0; row < rows; ++row) {
    fprintf(output, "QW %u", row);
    for (unsigned element = 0; element < QBS_BLOCK_ELEMENTS; ++element)
      fprintf(output, " %d", decoded_weight[row][element]);
    fputc('\n', output);
  }
  for (unsigned ctx = 0; ctx < m; ++ctx) {
    fprintf(output, "QA %u", ctx);
    for (unsigned element = 0; element < QBS_BLOCK_ELEMENTS; ++element)
      fprintf(output, " %d", decoded_activation[ctx][element]);
    fputc('\n', output);
  }

  const unsigned groups = profile == QBS_WEIGHT_PROFILE_Q4_K ? 8 : 16;
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
    const unsigned weight_d = profile == QBS_WEIGHT_PROFILE_Q4_K
                                  ? weights.q4[row].d
                                  : weights.q6[row].d;
    const unsigned weight_dmin = profile == QBS_WEIGHT_PROFILE_Q4_K
                                     ? weights.q4[row].dmin
                                     : 0;
    uint32_t activation_d;
    memcpy(&activation_d, &activations[ctx].d, sizeof(activation_d));
    fprintf(output,
            "R %u %" PRId32 " %" PRId32 " %04x %04x %08" PRIx32
            " %08" PRIx32 " %08" PRIx32 "\n",
            stream, expected.result_dot[stream], expected.result_aux[stream],
            weight_d, weight_dmin, activation_d,
            expected.result_fp_bits[stream],
            repeated_expected.result_fp_bits[stream]);
  }

  const unsigned k_per = m == 1 ? 8 : (m == 2 ? 4 : 2);
  const unsigned cycles = QBS_BLOCK_ELEMENTS / k_per;
  fprintf(output, "F %02" PRIx32 " %02" PRIx32 "\n", result.fflags,
          repeated_result.fflags);
  fprintf(output, "C %u %u %u\n", rows * m * QBS_BLOCK_ELEMENTS,
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

  const unsigned case_count = 2u * 4u * 4u * 3u;
  fprintf(output, "QBSV1 %u\n", case_count);
  unsigned case_id = 0;
  for (unsigned profile = QBS_WEIGHT_PROFILE_Q4_K;
       profile <= QBS_WEIGHT_PROFILE_Q6_K; ++profile) {
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
