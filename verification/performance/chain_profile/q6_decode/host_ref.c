#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "qbs_ref.h"

enum { KB = 8, K = 2048, N = 64, W = 210 * KB * N, A = 292 * KB };

static void fail(const char *message) {
  fprintf(stderr, "%s\n", message);
  exit(1);
}

static void load(const char *path, void *data, size_t size) {
  FILE *f = fopen(path, "rb");
  if (!f || fread(data, 1, size, f) != size || fgetc(f) != EOF)
    fail("Missing, short or overlong reference input");
  if (fclose(f)) fail("Reference input close failed");
}

static void save(const char *directory, const char *name, const void *p, size_t n) {
  char path[4096];
  if (snprintf(path, sizeof(path), "%s/%s", directory, name) >= (int)sizeof(path))
    fail("Output path too long");
  FILE *f = fopen(path, "wb");
  if (!f || fwrite(p, 1, n, f) != n || fclose(f)) fail("Cannot write golden");
}

int main(int argc, char **argv) {
  if (argc != 8) fail("host_ref input.f32 weights128 q8.old r4.old expected.old crop64 output");
  float input[K], expected[N], old_expected[128];
  unsigned char weights[W*2], r4[W*2], old_r4[W*2], crop[W], independent_crop[W];
  qbs_block_q8_k_t activation[KB], old_activation[KB];
  _Static_assert(sizeof(activation) == A, "Q8_K size");
  load(argv[1], input, sizeof(input));
  load(argv[2], weights, sizeof(weights));
  load(argv[3], old_activation, sizeof(old_activation));
  load(argv[4], old_r4, sizeof(old_r4));
  load(argv[5], old_expected, sizeof(old_expected));
  load(argv[6], crop, sizeof(crop));
  if (qbs_ref_quantize_q8_k(input, K, activation, KB) != QBS_REF_OK ||
      memcmp(activation, old_activation, A)) fail("Independent complete Q8 bytes disagree");
  if (qbs_ref_repack_weight_r4(QBS_WEIGHT_PROFILE_Q6_K, weights, sizeof(weights),
                              128, KB, r4, sizeof(r4)) != QBS_REF_OK ||
      memcmp(r4, old_r4, sizeof(r4))) fail("Captured R4 is not full-K independent repack");
  if (qbs_ref_repack_weight_r4(QBS_WEIGHT_PROFILE_Q6_K, weights, W, N, KB,
                              independent_crop, W) != QBS_REF_OK ||
      memcmp(crop, independent_crop, W)) fail("N64 crop layout mismatch");
  for (unsigned i = 0; i < 2; ++i) {
    const qbs_descriptor_fields_t fields = {
        .descriptor_version = QBS_DESCRIPTOR_VERSION,
        .weight_profile = QBS_WEIGHT_PROFILE_Q6_K,
        .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
        .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
        .activation_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR,
        .n = 32, .k_blocks = KB,
    };
    const qbs_descriptor_t descriptor = {
        .header = qbs_pack_descriptor_header(&fields), .weight_base = 0x81000000,
    };
    qbs_ref_result_t result;
    if (qbs_ref_execute(&descriptor, 1, 8, 1024, 0x82000000,
                        crop + i*32*KB*210, 32*KB*210, activation, A,
                        expected + i*32, 32, NULL, NULL, &result) != QBS_REF_OK)
      fail("Independent reference execution failed");
  }
  if (memcmp(expected, old_expected, sizeof(expected)))
    fail("Current reference golden differs from audited original first N64");
  save(argv[7], "activation_q8.bin", activation, A);
  save(argv[7], "expected.bin", expected, sizeof(expected));
  puts("HOST_Q6_REF_PASS full_q8_bytes=2336 full_r4_rows=128 cropped_rows=64 commands=2 k=2048");
  return 0;
}
