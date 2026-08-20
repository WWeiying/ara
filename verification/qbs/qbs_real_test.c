#include "qbs_ref.h"

#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
  const char *name;
  unsigned profile;
  unsigned m;
  unsigned n;
  unsigned k;
  const char *directory;
} case_config_t;

static void *read_exact_file(const char *path, size_t expected_bytes) {
  FILE *file = fopen(path, "rb");
  if (file == NULL) {
    fprintf(stderr, "cannot open %s: %s\n", path, strerror(errno));
    return NULL;
  }
  void *data = malloc(expected_bytes == 0 ? 1 : expected_bytes);
  if (data == NULL) {
    fprintf(stderr, "cannot allocate %zu bytes for %s\n", expected_bytes,
            path);
    fclose(file);
    return NULL;
  }
  const size_t count = fread(data, 1, expected_bytes, file);
  const int trailing = fgetc(file);
  if (count != expected_bytes || trailing != EOF) {
    fprintf(stderr, "%s has unexpected size (expected %zu bytes)\n", path,
            expected_bytes);
    free(data);
    fclose(file);
    return NULL;
  }
  if (fclose(file) != 0) {
    fprintf(stderr, "cannot close %s\n", path);
    free(data);
    return NULL;
  }
  return data;
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

static qbs_descriptor_v1_t make_descriptor(unsigned profile,
                                           unsigned weight_layout,
                                           unsigned activation_layout,
                                           unsigned n, unsigned k_blocks) {
  const qbs_descriptor_fields_t fields = {
      .descriptor_version = QBS_DESCRIPTOR_VERSION,
      .weight_profile = (uint8_t)profile,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
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

static int execute_layout(const case_config_t *config, const void *weights,
                          size_t block_bytes,
                          const qbs_block_q8_k_t *activation_row,
                          const qbs_block_q8_kx4_t *activation_m4,
                          unsigned weight_layout,
                          unsigned activation_layout, float *output) {
  const unsigned k_blocks = config->k / QBS_BLOCK_ELEMENTS;
  const void *activation = activation_layout == QBS_ACTIVATION_LAYOUT_ROW_MAJOR
                               ? (const void *)activation_row
                               : (const void *)activation_m4;
  const size_t activation_bytes = qbs_ref_activation_storage_bytes(
      activation_layout, config->m, k_blocks);
  for (unsigned first_row = 0; first_row < config->n;
       first_row += QBS_MAX_N) {
    const unsigned tile_n =
        config->n - first_row < QBS_MAX_N ? config->n - first_row : QBS_MAX_N;
    const uint8_t *row_tile =
        (const uint8_t *)weights +
        (size_t)first_row * k_blocks * block_bytes;
    const size_t row_tile_bytes = (size_t)tile_n * k_blocks * block_bytes;
    const void *weight_tile = row_tile;
    size_t weight_tile_bytes = row_tile_bytes;
    void *repacked = NULL;
    if (weight_layout == QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR) {
      weight_tile_bytes = qbs_ref_weight_storage_bytes(
          config->profile, weight_layout, tile_n, k_blocks);
      repacked = malloc(weight_tile_bytes);
      if (repacked == NULL) {
        fprintf(stderr, "%s: cannot allocate repacked tile\n", config->name);
        return 0;
      }
      const qbs_ref_status_t repack_status = qbs_ref_repack_weight_r4(
          config->profile, row_tile, row_tile_bytes, tile_n, k_blocks,
          repacked, weight_tile_bytes);
      if (repack_status != QBS_REF_OK) {
        fprintf(stderr, "%s: weight repack failed: %s\n", config->name,
                qbs_ref_status_string(repack_status));
        free(repacked);
        return 0;
      }
      weight_tile = repacked;
    }

    qbs_descriptor_v1_t descriptor = make_descriptor(
        config->profile, weight_layout, activation_layout, tile_n, k_blocks);
    float destination[QBS_MAX_M * QBS_MAX_N];
    for (unsigned index = 0; index < QBS_MAX_M * QBS_MAX_N; ++index)
      destination[index] = NAN;
    qbs_ref_result_t result = {0};
    const qbs_ref_status_t status = qbs_ref_execute(
        &descriptor, config->m, config->m == 1 ? 0 : 4, 1024,
        UINT64_C(0x2000), weight_tile, weight_tile_bytes, activation,
        activation_bytes, destination, QBS_MAX_M * QBS_MAX_N, NULL, NULL,
        &result);
    free(repacked);
    if (status != QBS_REF_OK) {
      fprintf(stderr, "%s: execute failed: %s\n", config->name,
              qbs_ref_status_string(status));
      return 0;
    }
    for (unsigned context = 0; context < config->m; ++context) {
      memcpy(output + (size_t)context * config->n + first_row,
             destination + context * QBS_MAX_N,
             tile_n * sizeof(float));
    }
  }
  return 1;
}

static int compare_layout(const char *case_name, const char *layout_name,
                          const float *reference, const float *actual,
                          size_t elements) {
  for (size_t index = 0; index < elements; ++index) {
    uint32_t reference_bits;
    uint32_t actual_bits;
    memcpy(&reference_bits, &reference[index], sizeof(reference_bits));
    memcpy(&actual_bits, &actual[index], sizeof(actual_bits));
    if (reference_bits != actual_bits) {
      fprintf(stderr,
              "%s: %s differs at element %zu: %.9g (0x%08x) vs %.9g "
              "(0x%08x)\n",
              case_name, layout_name, index, reference[index], reference_bits,
              actual[index], actual_bits);
      return 0;
    }
  }
  return 1;
}

static int compare_golden(const case_config_t *config, const float *actual,
                          const float *golden, size_t elements) {
  const float absolute_tolerance = 2.0e-3f;
  const float relative_tolerance = 2.0e-3f;
  float maximum_absolute = 0.0f;
  float maximum_relative = 0.0f;
  size_t worst_index = 0;
  size_t mismatch_count = 0;
  double checksum = 0.0;
  for (size_t index = 0; index < elements; ++index) {
    const float difference = fabsf(actual[index] - golden[index]);
    const float relative = difference / fmaxf(fabsf(golden[index]), 1.0e-30f);
    if (difference > maximum_absolute) {
      maximum_absolute = difference;
      worst_index = index;
    }
    if (relative > maximum_relative) maximum_relative = relative;
    if (!isfinite(actual[index]) || !isfinite(golden[index]) ||
        difference > absolute_tolerance + relative_tolerance * fabsf(golden[index]))
      ++mismatch_count;
    checksum += actual[index];
  }
  printf("case=%s profile=%s M=%u N=%u K=%u checksum=%.9e "
         "max_abs=%.9g max_rel=%.9g mismatches=%zu/%zu worst=%zu "
         "qbs=%.9g golden=%.9g\n",
         config->name,
         config->profile == QBS_WEIGHT_PROFILE_Q4_K ? "q4_K" : "q6_K",
         config->m, config->n, config->k, checksum, maximum_absolute,
         maximum_relative, mismatch_count, elements, worst_index,
         actual[worst_index], golden[worst_index]);
  return mismatch_count == 0;
}

int main(int argc, char **argv) {
  if (argc != 7) {
    fprintf(stderr,
            "usage: %s CASE q4_K|q6_K M N K GENERATED_DIRECTORY\n",
            argv[0]);
    return EXIT_FAILURE;
  }
  case_config_t config = {
      .name = argv[1],
      .profile = parse_profile(argv[2]),
      .directory = argv[6],
  };
  if (config.profile == QBS_WEIGHT_PROFILE_INVALID ||
      !parse_unsigned(argv[3], &config.m) ||
      !parse_unsigned(argv[4], &config.n) ||
      !parse_unsigned(argv[5], &config.k) || config.m == 0 ||
      config.m > QBS_MAX_M || config.n == 0 || config.k == 0 ||
      config.k % QBS_BLOCK_ELEMENTS != 0) {
    fprintf(stderr, "%s: invalid case configuration\n", config.name);
    return EXIT_FAILURE;
  }

  const size_t block_bytes = config.profile == QBS_WEIGHT_PROFILE_Q4_K
                                 ? QBS_Q4_K_BLOCK_BYTES
                                 : QBS_Q6_K_BLOCK_BYTES;
  const unsigned k_blocks = config.k / QBS_BLOCK_ELEMENTS;
  const size_t weight_bytes = (size_t)config.n * k_blocks * block_bytes;
  const size_t activation_elements = (size_t)config.m * config.k;
  const size_t output_elements = (size_t)config.m * config.n;
  char path[4096];
  if (snprintf(path, sizeof(path), "%s/source_weight.bin", config.directory) >=
      (int)sizeof(path))
    return EXIT_FAILURE;
  void *weights = read_exact_file(path, weight_bytes);
  if (snprintf(path, sizeof(path), "%s/activation_f32.bin", config.directory) >=
      (int)sizeof(path)) {
    free(weights);
    return EXIT_FAILURE;
  }
  float *activation_f32 =
      read_exact_file(path, activation_elements * sizeof(float));
  if (snprintf(path, sizeof(path), "%s/golden_f32.bin", config.directory) >=
      (int)sizeof(path)) {
    free(weights);
    free(activation_f32);
    return EXIT_FAILURE;
  }
  float *golden = read_exact_file(path, output_elements * sizeof(float));
  if (weights == NULL || activation_f32 == NULL || golden == NULL) {
    free(weights);
    free(activation_f32);
    free(golden);
    return EXIT_FAILURE;
  }

  qbs_block_q8_k_t *activation_row =
      malloc((size_t)config.m * k_blocks * sizeof(*activation_row));
  qbs_block_q8_kx4_t *activation_m4 =
      config.m == 4 ? malloc(k_blocks * sizeof(*activation_m4)) : NULL;
  float *row_row = malloc(output_elements * sizeof(float));
  float *r4_row = malloc(output_elements * sizeof(float));
  float *row_m4 = config.m == 4 ? malloc(output_elements * sizeof(float)) : NULL;
  float *r4_m4 = config.m == 4 ? malloc(output_elements * sizeof(float)) : NULL;
  if (activation_row == NULL || row_row == NULL || r4_row == NULL ||
      (config.m == 4 &&
       (activation_m4 == NULL || row_m4 == NULL || r4_m4 == NULL))) {
    fprintf(stderr, "%s: allocation failure\n", config.name);
    free(weights);
    free(activation_f32);
    free(golden);
    free(activation_row);
    free(activation_m4);
    free(row_row);
    free(r4_row);
    free(row_m4);
    free(r4_m4);
    return EXIT_FAILURE;
  }

  int ok = qbs_ref_quantize_q8_k(
               activation_f32, activation_elements, activation_row,
               (size_t)config.m * k_blocks) == QBS_REF_OK;
  if (ok && config.m == 4) {
    ok = qbs_ref_pack_activation_m4(
             activation_row, (size_t)config.m * k_blocks, k_blocks,
             activation_m4, k_blocks) == QBS_REF_OK;
  }
  if (ok)
    ok = execute_layout(&config, weights, block_bytes, activation_row,
                        activation_m4, QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                        QBS_ACTIVATION_LAYOUT_ROW_MAJOR, row_row);
  if (ok)
    ok = execute_layout(&config, weights, block_bytes, activation_row,
                        activation_m4, QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                        QBS_ACTIVATION_LAYOUT_ROW_MAJOR, r4_row);
  if (ok)
    ok = compare_layout(config.name, "R4+row", row_row, r4_row,
                        output_elements);
  if (ok && config.m == 4)
    ok = execute_layout(&config, weights, block_bytes, activation_row,
                        activation_m4, QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                        QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED, row_m4);
  if (ok && config.m == 4)
    ok = compare_layout(config.name, "row+M4", row_row, row_m4,
                        output_elements);
  if (ok && config.m == 4)
    ok = execute_layout(&config, weights, block_bytes, activation_row,
                        activation_m4, QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                        QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED, r4_m4);
  if (ok && config.m == 4)
    ok = compare_layout(config.name, "R4+M4", row_row, r4_m4,
                        output_elements);
  if (ok) ok = compare_golden(&config, row_row, golden, output_elements);

  free(weights);
  free(activation_f32);
  free(golden);
  free(activation_row);
  free(activation_m4);
  free(row_row);
  free(r4_row);
  free(row_m4);
  free(r4_m4);
  return ok ? EXIT_SUCCESS : EXIT_FAILURE;
}
