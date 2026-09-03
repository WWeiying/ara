#include "qbs_ref.h"

#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <math.h>
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

static int emit_case_data(FILE *output, unsigned case_id, unsigned profile,
                          unsigned weight_layout,
                          unsigned activation_layout, unsigned m, unsigned n,
                          unsigned k_blocks,
                          const uint8_t *source_row_weights,
                          const float *source_activations,
                          const float *captured_golden) {
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

  if (source_row_weights != NULL) {
    memcpy(row_weights, source_row_weights, row_weight_bytes);
  } else {
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
  }
  if (source_activations != NULL) {
    if (activation_profile != QBS_ACTIVATION_PROFILE_Q8_K ||
        qbs_ref_quantize_q8_k(source_activations,
                              (size_t)m * k_blocks * block_elements,
                              (qbs_block_q8_k_t *)row_activations,
                              row_activation_blocks) != QBS_REF_OK) {
      fprintf(stderr, "activation quantization failure for command case %u\n",
              case_id);
      return 1;
    }
  } else {
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
  }

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
  } else if (activation_layout == QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED) {
    if (qbs_ref_pack_activation_m8_profile(
            activation_profile, row_activations, row_activation_bytes, m,
            k_blocks, layout_activations, layout_activation_bytes) !=
        QBS_REF_OK) {
      fprintf(stderr, "M8 activation pack failure for command case %u\n",
              case_id);
      return 1;
    }
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
  qbs_descriptor_t descriptor __attribute__((aligned(16))) = {
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

  if (captured_golden != NULL) {
    float maximum_absolute = 0.0f;
    float maximum_relative = 0.0f;
    for (unsigned ctx = 0; ctx < m; ++ctx) {
      for (unsigned row = 0; row < n; ++row) {
        const float actual = destination[(size_t)ctx * 32u + row];
        const float golden = captured_golden[(size_t)ctx * n + row];
        const float absolute = fabsf(actual - golden);
        const float relative = absolute / fmaxf(fabsf(golden), 1.0e-30f);
        if (absolute > maximum_absolute) maximum_absolute = absolute;
        if (relative > maximum_relative) maximum_relative = relative;
        if (!isfinite(actual) || !isfinite(golden) ||
            absolute > 2.0e-3f + 2.0e-3f * fabsf(golden)) {
          fprintf(stderr,
                  "real command case %u differs at context=%u row=%u: "
                  "qbs=%.9g golden=%.9g abs=%.9g rel=%.9g\n",
                  case_id, ctx, row, actual, golden, absolute, relative);
          return 1;
        }
      }
    }
    fprintf(stderr,
            "real command case %u reference PASS M=%u N=%u K=%u "
            "max_abs=%.9g max_rel=%.9g\n",
            case_id, m, n, k_blocks * block_elements, maximum_absolute,
            maximum_relative);
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
          const unsigned storage_m =
              activation_layout == QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED
                  ? QBS_MAX_M : 4u;
          const uint8_t *block = layout_activations +
              (size_t)kb * storage_m * activation_block_bytes;
          for (unsigned offset = 0;
               offset < storage_m * activation_block_bytes; offset += 16)
            print_beat(output, "A", 0, offset, block,
                       (unsigned)(storage_m * activation_block_bytes));
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
      const unsigned accumulator_stride =
          m >= QBS_WIDE_M_MIN ? QBS_WIDE_M_MAX_N : QBS_MAX_N;
      fprintf(output, "O %u %08" PRIx32 "\n",
              ctx * accumulator_stride + row, bits);
    }
  }

  const unsigned first_wave_m = m < 4u ? m : 4u;
  const unsigned second_wave_m = m > 4u ? m - 4u : 0u;
  const unsigned first_k_per =
      first_wave_m == 1 ? 8u : (first_wave_m == 2 ? 4u : 2u);
  const unsigned second_k_per = second_wave_m == 0 ? 0u :
      (second_wave_m == 1 ? 8u : (second_wave_m == 2 ? 4u : 2u));
  const unsigned dot_cycles_per_logical_tile =
      block_elements / first_k_per +
      (second_k_per == 0 ? 0u : block_elements / second_k_per);
  const unsigned logical_tiles = k_blocks * ((n + 3u) / 4u);
  const unsigned waves = second_wave_m == 0 ? 1u : 2u;
  const unsigned uops_per_output =
      qbs_weight_correction_mode(profile) == QBS_CORRECTION_AFFINE_MIN ? 6 : 3;
  fprintf(output,
          "C %u %zu %zu %u %u %u %u %u\n",
          logical_tiles * waves, (size_t)n * k_blocks * block_bytes,
          layout_activation_bytes,
          m * n * k_blocks * block_elements,
          n * k_blocks * dot_cycles_per_logical_tile * 8u,
          logical_tiles * dot_cycles_per_logical_tile,
          m * n * k_blocks * uops_per_output,
          m * n * k_blocks);
  fprintf(output, "END\n");

  free(layout_activations);
  free(row_activations);
  free(layout_weights);
  free(row_weights);
  return 0;
}

static int emit_case(FILE *output, unsigned case_id, unsigned profile,
                     unsigned weight_layout, unsigned activation_layout,
                     unsigned m, unsigned n, unsigned k_blocks) {
  return emit_case_data(output, case_id, profile, weight_layout,
                        activation_layout, m, n, k_blocks, NULL, NULL, NULL);
}

static int parse_unsigned(const char *text, unsigned *value) {
  char *end = NULL;
  errno = 0;
  const unsigned long parsed = strtoul(text, &end, 10);
  if (errno != 0 || end == text || *end != '\0' || parsed > UINT32_MAX)
    return 0;
  *value = (unsigned)parsed;
  return 1;
}

static unsigned parse_profile(const char *text) {
  if (strcmp(text, "q4_K") == 0) return QBS_WEIGHT_PROFILE_Q4_K;
  if (strcmp(text, "q6_K") == 0) return QBS_WEIGHT_PROFILE_Q6_K;
  return QBS_WEIGHT_PROFILE_INVALID;
}

static int read_slice(const char *path, size_t offset, void *data,
                      size_t bytes) {
  FILE *input = fopen(path, "rb");
  if (input == NULL) {
    fprintf(stderr, "cannot open %s: %s\n", path, strerror(errno));
    return 0;
  }
  int ok = offset <= (size_t)LONG_MAX &&
           fseek(input, (long)offset, SEEK_SET) == 0 &&
           fread(data, 1, bytes, input) == bytes;
  if (!ok)
    fprintf(stderr, "cannot read [%zu,%zu) from %s\n", offset,
            offset + bytes, path);
  if (fclose(input) != 0) ok = 0;
  return ok;
}

static int emit_real_case(FILE *output, unsigned profile,
                          const char *directory, unsigned full_n, unsigned k,
                          unsigned input_start, unsigned m,
                          unsigned output_start, unsigned n) {
  const size_t block_bytes = qbs_weight_block_bytes(profile);
  const unsigned block_elements = qbs_weight_block_elements(profile);
  if (block_bytes == 0 || block_elements == 0 || k % block_elements != 0 ||
      m == 0 || m > QBS_MAX_M || n == 0 ||
      n > (m >= QBS_WIDE_M_MIN ? QBS_WIDE_M_MAX_N : QBS_MAX_N) ||
      output_start > full_n ||
      n > full_n - output_start) {
    fprintf(stderr, "invalid real command slice\n");
    return 1;
  }
  const unsigned k_blocks = k / block_elements;
  const size_t row_weight_bytes = (size_t)k_blocks * block_bytes;
  const size_t weight_bytes = (size_t)n * row_weight_bytes;
  const size_t activation_elements = (size_t)m * k;
  const size_t output_elements = (size_t)m * n;
  uint8_t *weights = malloc(weight_bytes);
  float *activations = malloc(activation_elements * sizeof(*activations));
  float *golden = malloc(output_elements * sizeof(*golden));
  char path[4096];
  int ok = weights != NULL && activations != NULL && golden != NULL;

  const char *weight_name = profile == QBS_WEIGHT_PROFILE_Q4_K
      ? "weight_q4_K.bin" : "weight_q6_K.bin";
  if (ok && snprintf(path, sizeof(path), "%s/%s", directory, weight_name) <
                (int)sizeof(path))
    ok = read_slice(path, (size_t)output_start * row_weight_bytes, weights,
                    weight_bytes);
  else
    ok = 0;
  if (ok && snprintf(path, sizeof(path), "%s/activation_f32.bin", directory) <
                (int)sizeof(path))
    ok = read_slice(path, (size_t)input_start * k * sizeof(float), activations,
                    activation_elements * sizeof(*activations));
  else
    ok = 0;
  if (ok && snprintf(path, sizeof(path), "%s/output_f32.bin", directory) <
                (int)sizeof(path)) {
    for (unsigned ctx = 0; ctx < m && ok; ++ctx)
      ok = read_slice(path,
                      ((size_t)(input_start + ctx) * full_n + output_start) *
                          sizeof(float),
                      golden + (size_t)ctx * n, n * sizeof(*golden));
  } else {
    ok = 0;
  }

  if (ok) {
    const unsigned activation_layout = m >= QBS_WIDE_M_MIN
        ? QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED
        : (m == 4 ? QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED
                  : QBS_ACTIVATION_LAYOUT_ROW_MAJOR);
    fprintf(output, "QBSCMD1 1\n");
    ok = emit_case_data(output, 0, profile,
                        QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                        activation_layout, m, n, k_blocks,
                        weights, activations, golden) == 0;
  }
  free(golden);
  free(activations);
  free(weights);
  return ok ? 0 : 1;
}

int main(int argc, char **argv) {
  if (argc != 2 && argc != 11) {
    fprintf(stderr,
            "usage: %s OUTPUT\n"
            "       %s OUTPUT --real q4_K|q6_K DIRECTORY FULL_N K "
            "INPUT_START M OUTPUT_START N\n",
            argv[0], argv[0]);
    return 2;
  }
  FILE *output = fopen(argv[1], "w");
  if (output == NULL) {
    perror(argv[1]);
    return 2;
  }
  if (argc == 11) {
    unsigned profile = parse_profile(argv[3]);
    unsigned full_n, k, input_start, m, output_start, n;
    int failed = strcmp(argv[2], "--real") != 0 ||
                 profile == QBS_WEIGHT_PROFILE_INVALID ||
                 !parse_unsigned(argv[5], &full_n) ||
                 !parse_unsigned(argv[6], &k) ||
                 !parse_unsigned(argv[7], &input_start) ||
                 !parse_unsigned(argv[8], &m) ||
                 !parse_unsigned(argv[9], &output_start) ||
                 !parse_unsigned(argv[10], &n);
    if (!failed)
      failed = emit_real_case(output, profile, argv[4], full_n, k,
                              input_start, m, output_start, n);
    fclose(output);
    if (failed) return 1;
    printf("wrote real QBS command slice to %s\n", argv[1]);
    return 0;
  }

  fprintf(output, "QBSCMD1 33\n");
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
  failed |= emit_case(output, 22, QBS_WEIGHT_PROFILE_Q4_K,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED, 5, 15, 1);
  failed |= emit_case(output, 23, QBS_WEIGHT_PROFILE_Q6_K,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED, 8, 16, 1);
  // Exercise the distinct two- and three-context second-wave schedules.
  failed |= emit_case(output, 24, QBS_WEIGHT_PROFILE_Q4_K,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED, 6, 11, 1);
  failed |= emit_case(output, 25, QBS_WEIGHT_PROFILE_Q6_K,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED, 7, 13, 1);
  // The M8 layout is profile-generic. Keep one short wide command for every
  // remaining advertised weight profile so ABI coverage matches capability.
  failed |= emit_case(output, 26, QBS_WEIGHT_PROFILE_Q5_K,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED, 8, 9, 1);
  failed |= emit_case(output, 27, QBS_WEIGHT_PROFILE_Q3_K,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED, 5, 16, 1);
  failed |= emit_case(output, 28, QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED, 8, 7, 1);
  failed |= emit_case(output, 29, QBS_WEIGHT_PROFILE_Q4_0,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED, 6, 12, 1);
  failed |= emit_case(output, 30, QBS_WEIGHT_PROFILE_Q2_K,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED, 7, 15, 1);
  failed |= emit_case(output, 31, QBS_WEIGHT_PROFILE_Q5_0,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED, 8, 16, 1);
  failed |= emit_case(output, 32, QBS_WEIGHT_PROFILE_IQ4_NL,
                      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                      QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED, 5, 11, 1);
  fclose(output);
  if (failed) return 1;
  printf("wrote 33 QBS command cases to %s\n", argv[1]);
  return 0;
}
