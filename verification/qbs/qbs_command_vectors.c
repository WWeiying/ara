#include "qbs_ref.h"

#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint32_t random_state = UINT32_C(0x51425343);

static uint32_t next_random(void) {
  random_state = random_state * UINT32_C(1664525) + UINT32_C(1013904223);
  return random_state;
}

static size_t weight_block_bytes(unsigned profile) {
  return qbs_weight_block_bytes(profile);
}

static void fill_q4(qbs_block_q4_k_t *block, unsigned row, unsigned kb) {
  block->d = (qbs_fp16_t)(UINT16_C(0x3400) + row * 7u + kb * 3u);
  block->dmin = (qbs_fp16_t)(UINT16_C(0x2c00) + row * 5u + kb * 2u);
  for (size_t i = 0; i < sizeof(block->scales); ++i)
    block->scales[i] = (uint8_t)next_random();
  for (size_t i = 0; i < sizeof(block->qs); ++i)
    block->qs[i] = (uint8_t)next_random();
}

static void fill_q5(qbs_block_q5_k_t *block, unsigned row, unsigned kb) {
  block->d = (qbs_fp16_t)(UINT16_C(0x3400) + row * 7u + kb * 3u);
  block->dmin = (qbs_fp16_t)(UINT16_C(0x2c00) + row * 5u + kb * 2u);
  for (size_t i = 0; i < sizeof(block->scales); ++i)
    block->scales[i] = (uint8_t)next_random();
  for (size_t i = 0; i < sizeof(block->qh); ++i)
    block->qh[i] = (uint8_t)next_random();
  for (size_t i = 0; i < sizeof(block->qs); ++i)
    block->qs[i] = (uint8_t)next_random();
}

static void fill_q6(qbs_block_q6_k_t *block, unsigned row, unsigned kb) {
  block->d = (qbs_fp16_t)(UINT16_C(0x3400) + row * 5u + kb * 2u);
  for (size_t i = 0; i < sizeof(block->ql); ++i)
    block->ql[i] = (uint8_t)next_random();
  for (size_t i = 0; i < sizeof(block->qh); ++i)
    block->qh[i] = (uint8_t)next_random();
  for (size_t i = 0; i < sizeof(block->scales); ++i)
    block->scales[i] = (int8_t)((int)(next_random() & 0x1fu) - 16);
}

static void fill_q3(qbs_block_q3_k_t *block, unsigned row, unsigned kb) {
  block->d = (qbs_fp16_t)(UINT16_C(0x3400) + row * 5u + kb * 2u);
  for (size_t i = 0; i < sizeof(block->hmask); ++i)
    block->hmask[i] = (uint8_t)next_random();
  for (size_t i = 0; i < sizeof(block->qs); ++i)
    block->qs[i] = (uint8_t)next_random();
  for (size_t i = 0; i < sizeof(block->scales); ++i)
    block->scales[i] = (uint8_t)next_random();
}

static void fill_q8_0_weight(qbs_block_q8_0_t *block, unsigned row,
                             unsigned kb) {
  block->d = (qbs_fp16_t)(UINT16_C(0x3400) + row * 5u + kb * 2u);
  for (size_t i = 0; i < sizeof(block->qs); ++i)
    block->qs[i] = (int8_t)((int)(next_random() & 0xffu) - 128);
}

static void fill_q4_0(qbs_block_q4_0_t *block, unsigned row, unsigned kb) {
  block->d = (qbs_fp16_t)(UINT16_C(0x3400) + row * 5u + kb * 2u);
  for (size_t i = 0; i < sizeof(block->qs); ++i)
    block->qs[i] = (uint8_t)next_random();
}

static void fill_q2(qbs_block_q2_k_t *block, unsigned row, unsigned kb) {
  block->d = (qbs_fp16_t)(UINT16_C(0x3400) + row * 7u + kb * 3u);
  block->dmin = (qbs_fp16_t)(UINT16_C(0x2c00) + row * 5u + kb * 2u);
  for (size_t i = 0; i < sizeof(block->scales); ++i)
    block->scales[i] = (uint8_t)next_random();
  for (size_t i = 0; i < sizeof(block->qs); ++i)
    block->qs[i] = (uint8_t)next_random();
}

static void fill_q5_0(qbs_block_q5_0_t *block, unsigned row, unsigned kb) {
  block->d = (qbs_fp16_t)(UINT16_C(0x3400) + row * 5u + kb * 2u);
  for (size_t i = 0; i < sizeof(block->qh); ++i)
    block->qh[i] = (uint8_t)next_random();
  for (size_t i = 0; i < sizeof(block->qs); ++i)
    block->qs[i] = (uint8_t)next_random();
}

static void fill_iq4_nl(qbs_block_iq4_nl_t *block, unsigned row,
                        unsigned kb) {
  block->d = (qbs_fp16_t)(UINT16_C(0x3400) + row * 5u + kb * 2u);
  for (size_t i = 0; i < sizeof(block->qs); ++i)
    block->qs[i] = (uint8_t)next_random();
}

static unsigned activation_profile_for_weight(unsigned profile) {
  return qbs_default_activation_profile(profile);
}

static void fill_activation(qbs_block_q8_k_t *block, unsigned ctx,
                            unsigned kb) {
  uint32_t d_bits = UINT32_C(0x3e800000) + (ctx << 18) + (kb << 14);
  memcpy(&block->d, &d_bits, sizeof(d_bits));
  for (unsigned i = 0; i < QBS_BLOCK_ELEMENTS; ++i)
    block->qs[i] = (int8_t)((int)(next_random() & 0xffu) - 128);
  for (unsigned group = 0; group < 16; ++group) {
    int sum = 0;
    for (unsigned item = 0; item < 16; ++item)
      sum += block->qs[group * 16u + item];
    block->bsums[group] = (int16_t)sum;
  }
}

static void fill_activation_q8_0(qbs_block_q8_0_t *block, unsigned ctx,
                                 unsigned kb) {
  block->d = (qbs_fp16_t)(UINT16_C(0x3400) + ctx * 5u + kb * 2u);
  for (unsigned i = 0; i < QBS_Q8_0_BLOCK_ELEMENTS; ++i)
    block->qs[i] = (int8_t)((int)(next_random() & 0xffu) - 128);
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

static const uint8_t *weight_address(const uint8_t *storage,
                                     unsigned layout, unsigned row,
                                     unsigned kb, unsigned k_blocks,
                                     size_t block_bytes) {
  size_t index = (size_t)row * k_blocks + kb;
  if (layout == QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR)
    index = ((size_t)(row / 4u) * k_blocks + kb) * 4u + row % 4u;
  return storage + index * block_bytes;
}

static int emit_case(FILE *output, unsigned case_id, unsigned profile,
                     unsigned weight_layout, unsigned activation_layout,
                     unsigned m, unsigned n, unsigned k_blocks) {
  const size_t block_bytes = weight_block_bytes(profile);
  const unsigned activation_profile = activation_profile_for_weight(profile);
  const size_t activation_block_bytes =
      qbs_activation_block_bytes(activation_profile);
  const unsigned block_elements = qbs_weight_block_elements(profile);
  const size_t row_weight_bytes = (size_t)n * k_blocks * block_bytes;
  const size_t layout_weight_bytes = qbs_ref_weight_storage_bytes(
      profile, weight_layout, n, k_blocks);
  const size_t row_activation_blocks = (size_t)m * k_blocks;
  const size_t row_activation_bytes =
      row_activation_blocks * activation_block_bytes;
  const size_t layout_activation_bytes =
      qbs_ref_activation_storage_bytes_for_profile(
          activation_profile, activation_layout, m, k_blocks);
  uint8_t *row_weights = calloc(1, row_weight_bytes);
  uint8_t *layout_weights = calloc(1, layout_weight_bytes);
  uint8_t *row_activations = calloc(1, row_activation_bytes);
  uint8_t *layout_activations = calloc(1, layout_activation_bytes);
  float destination[QBS_MAX_M * 32] = {0};
  qbs_ref_result_t result;
  if (row_weights == NULL || layout_weights == NULL ||
      row_activations == NULL || layout_activations == NULL) {
    fprintf(stderr, "allocation failure for command case %u\n", case_id);
    return 1;
  }

  for (unsigned row = 0; row < n; ++row) {
    for (unsigned kb = 0; kb < k_blocks; ++kb) {
      uint8_t *address = row_weights +
          ((size_t)row * k_blocks + kb) * block_bytes;
      if (profile == QBS_WEIGHT_PROFILE_Q4_K)
        fill_q4((qbs_block_q4_k_t *)address, row, kb);
      else if (profile == QBS_WEIGHT_PROFILE_Q5_K)
        fill_q5((qbs_block_q5_k_t *)address, row, kb);
      else if (profile == QBS_WEIGHT_PROFILE_Q6_K)
        fill_q6((qbs_block_q6_k_t *)address, row, kb);
      else if (profile == QBS_WEIGHT_PROFILE_Q3_K)
        fill_q3((qbs_block_q3_k_t *)address, row, kb);
      else if (profile == QBS_WEIGHT_PROFILE_Q8_0_WEIGHT)
        fill_q8_0_weight((qbs_block_q8_0_t *)address, row, kb);
      else if (profile == QBS_WEIGHT_PROFILE_Q4_0)
        fill_q4_0((qbs_block_q4_0_t *)address, row, kb);
      else if (profile == QBS_WEIGHT_PROFILE_Q2_K)
        fill_q2((qbs_block_q2_k_t *)address, row, kb);
      else if (profile == QBS_WEIGHT_PROFILE_Q5_0)
        fill_q5_0((qbs_block_q5_0_t *)address, row, kb);
      else if (profile == QBS_WEIGHT_PROFILE_IQ4_NL)
        fill_iq4_nl((qbs_block_iq4_nl_t *)address, row, kb);
      else {
        fprintf(stderr, "unsupported profile %u\n", profile);
        return 1;
      }
    }
  }
  for (unsigned ctx = 0; ctx < m; ++ctx)
    for (unsigned kb = 0; kb < k_blocks; ++kb)
      if (activation_profile == QBS_ACTIVATION_PROFILE_Q8_K)
        fill_activation(
            (qbs_block_q8_k_t *)(row_activations +
                                 ((size_t)ctx * k_blocks + kb) *
                                     activation_block_bytes),
            ctx, kb);
      else
        fill_activation_q8_0(
            (qbs_block_q8_0_t *)(row_activations +
                                 ((size_t)ctx * k_blocks + kb) *
                                     activation_block_bytes),
            ctx, kb);

  if (weight_layout == QBS_WEIGHT_LAYOUT_ROW_MAJOR) {
    memcpy(layout_weights, row_weights, row_weight_bytes);
  } else if (qbs_ref_repack_weight_r4(
                 profile, row_weights, row_weight_bytes, n, k_blocks,
                 layout_weights, layout_weight_bytes) != QBS_REF_OK) {
    fprintf(stderr, "weight repack failure for command case %u\n", case_id);
    return 1;
  }
  if (activation_layout == QBS_ACTIVATION_LAYOUT_ROW_MAJOR) {
    memcpy(layout_activations, row_activations, layout_activation_bytes);
  } else if (qbs_ref_pack_activation_m4_profile(
                 activation_profile, row_activations, row_activation_bytes,
                 k_blocks, layout_activations, layout_activation_bytes) !=
             QBS_REF_OK) {
    fprintf(stderr, "activation pack failure for command case %u\n",
            case_id);
    return 1;
  }

  const qbs_descriptor_fields_t fields = {
      .descriptor_version = QBS_DESCRIPTOR_VERSION,
      .weight_profile = (uint8_t)profile,
      .activation_profile = (uint8_t)activation_profile,
      .weight_layout = (uint8_t)weight_layout,
      .activation_layout = (uint8_t)activation_layout,
      .n = (uint8_t)n,
      .k_blocks = (uint16_t)k_blocks,
  };
  qbs_descriptor_v1_t descriptor __attribute__((aligned(16))) = {
      .header = qbs_pack_descriptor_header(&fields),
      .weight_base = (uintptr_t)layout_weights,
  };
  const qbs_ref_status_t status = qbs_ref_execute(
      &descriptor, m, 0, 1024, (uintptr_t)layout_activations,
      layout_weights, layout_weight_bytes, layout_activations,
      layout_activation_bytes, destination,
      sizeof(destination) / sizeof(destination[0]), NULL, NULL, &result);
  if (status != QBS_REF_OK) {
    fprintf(stderr, "command case %u failed: %s\n", case_id,
            qbs_ref_status_string(status));
    return 1;
  }

  fprintf(output, "CMD %u %u %u %u %u %u %u %02" PRIx32 "\n", case_id,
          profile, weight_layout, activation_layout, m, n, k_blocks,
          result.fflags);
  for (unsigned kb = 0; kb < k_blocks; ++kb) {
    for (unsigned row_base = 0; row_base < n; row_base += 4) {
      const unsigned rows = n - row_base < 4 ? n - row_base : 4;
      fprintf(output, "T %u %u %u\n", kb, row_base, rows);
      if (row_base == 0) {
        if (activation_layout == QBS_ACTIVATION_LAYOUT_ROW_MAJOR) {
          for (unsigned ctx = 0; ctx < m; ++ctx) {
            const uint8_t *block = layout_activations +
                ((size_t)ctx * k_blocks + kb) * activation_block_bytes;
            for (unsigned offset = 0; offset < activation_block_bytes;
                 offset += 16)
              print_beat(output, "A", ctx, offset, block,
                         (unsigned)activation_block_bytes);
          }
        } else {
          const uint8_t *block = layout_activations +
              (size_t)kb * 4u * activation_block_bytes;
          for (unsigned offset = 0;
               offset < 4u * activation_block_bytes; offset += 16)
            print_beat(output, "A", 0, offset, block,
                       (unsigned)(4u * activation_block_bytes));
        }
      }
      for (unsigned row = 0; row < rows; ++row) {
        const uint8_t *block = weight_address(
            layout_weights, weight_layout, row_base + row, kb, k_blocks,
            block_bytes);
        for (unsigned offset = 0; offset < block_bytes; offset += 16)
          print_beat(output, "W", row, offset, block,
                     (unsigned)block_bytes);
      }
      fprintf(output, "ENDT\n");
    }
  }
  for (unsigned ctx = 0; ctx < m; ++ctx) {
    for (unsigned row = 0; row < n; ++row) {
      uint32_t bits;
      memcpy(&bits, &destination[(size_t)ctx * 32u + row], sizeof(bits));
      fprintf(output, "O %u %08" PRIx32 "\n", ctx * 32u + row, bits);
    }
  }

  const unsigned k_per = m == 1 ? 8 : (m == 2 ? 4 : 2);
  const unsigned dot_cycles_per_tile = block_elements / k_per;
  const unsigned tiles = k_blocks * ((n + 3u) / 4u);
  const unsigned uops_per_output =
      qbs_weight_correction_mode(profile) == QBS_CORRECTION_AFFINE_MIN ? 6 : 3;
  fprintf(output,
          "C %u %zu %zu %u %u %u %u %u\n",
          tiles, (size_t)n * k_blocks * block_bytes,
          (size_t)m * k_blocks * activation_block_bytes,
          m * n * k_blocks * block_elements,
          n * k_blocks * dot_cycles_per_tile * 8u,
          tiles * dot_cycles_per_tile,
          m * n * k_blocks * uops_per_output,
          m * n * k_blocks);
  fprintf(output, "END\n");

  free(layout_activations);
  free(row_activations);
  free(layout_weights);
  free(row_weights);
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
  fprintf(output, "QBSCMD1 22\n");
  int failed = 0;
  failed |= emit_case(output, 0, QBS_WEIGHT_PROFILE_Q4_K,
                      QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                      QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 1, 5, 2);
  failed |= emit_case(output, 1, QBS_WEIGHT_PROFILE_Q4_K,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED, 4, 7, 2);
  failed |= emit_case(output, 2, QBS_WEIGHT_PROFILE_Q6_K,
                      QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                      QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 3, 3, 2);
  failed |= emit_case(output, 3, QBS_WEIGHT_PROFILE_Q6_K,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED, 4, 8, 3);
  // Decode-shaped R4 case: three alternating banks per K-block and a
  // one-row tail exercise response-owned bank/row metadata.
  failed |= emit_case(output, 4, QBS_WEIGHT_PROFILE_Q4_K,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 1, 9, 3);
  failed |= emit_case(output, 5, QBS_WEIGHT_PROFILE_Q4_0,
                      QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                      QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 1, 5, 3);
  failed |= emit_case(output, 6, QBS_WEIGHT_PROFILE_Q4_0,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED, 4, 7, 4);
  failed |= emit_case(output, 7, QBS_WEIGHT_PROFILE_Q4_0,
                      QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                      QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 1, 1, 65);
  failed |= emit_case(output, 8, QBS_WEIGHT_PROFILE_Q5_K,
                      QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                      QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 1, 5, 2);
  failed |= emit_case(output, 9, QBS_WEIGHT_PROFILE_Q5_K,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED, 4, 7, 3);
  failed |= emit_case(output, 10, QBS_WEIGHT_PROFILE_Q3_K,
                      QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                      QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 1, 5, 2);
  failed |= emit_case(output, 11, QBS_WEIGHT_PROFILE_Q3_K,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED, 4, 7, 3);
  failed |= emit_case(output, 12, QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
                      QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                      QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 1, 5, 3);
  failed |= emit_case(output, 13, QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED, 4, 7, 4);
  // GGML prefill tails retain R4 weights but use row-major activations.
  failed |= emit_case(output, 14, QBS_WEIGHT_PROFILE_Q4_K,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 2, 3, 2);
  failed |= emit_case(output, 15, QBS_WEIGHT_PROFILE_Q4_0,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 3, 5, 3);
  failed |= emit_case(output, 16, QBS_WEIGHT_PROFILE_Q2_K,
                      QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                      QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 1, 5, 2);
  failed |= emit_case(output, 17, QBS_WEIGHT_PROFILE_Q2_K,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED, 4, 7, 3);
  failed |= emit_case(output, 18, QBS_WEIGHT_PROFILE_Q5_0,
                      QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                      QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 1, 5, 3);
  failed |= emit_case(output, 19, QBS_WEIGHT_PROFILE_Q5_0,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED, 4, 7, 4);
  failed |= emit_case(output, 20, QBS_WEIGHT_PROFILE_IQ4_NL,
                      QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                      QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 1, 5, 3);
  failed |= emit_case(output, 21, QBS_WEIGHT_PROFILE_IQ4_NL,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED, 4, 7, 4);
  fclose(output);
  if (failed) return 1;
  printf("wrote 22 QBS command cases to %s\n", argv[1]);
  return 0;
}
