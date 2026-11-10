#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "qbs_ref.h"

enum { M = 8, K = 2048, KB = 8, MAX_N = 128, AB = M * KB * 292 };

static void require(int ok, const char *message) {
  if (!ok) { fprintf(stderr, "%s\n", message); exit(1); }
}

static void load(const char *path, void *data, size_t bytes) {
  FILE *f = fopen(path, "rb");
  require(f != NULL, "Cannot open capture");
  require(fread(data, 1, bytes, f) == bytes && fgetc(f) == EOF,
          "Capture size mismatch");
  require(fclose(f) == 0, "Cannot close capture");
}

static void save(const char *directory, const char *name, const void *data, size_t bytes) {
  char path[4096];
  require(snprintf(path, sizeof(path), "%s/%s", directory, name) < (int)sizeof(path),
          "Output path too long");
  FILE *f = fopen(path, "wb");
  require(f != NULL, "Cannot create reference");
  require(fwrite(data, 1, bytes, f) == bytes && fclose(f) == 0, "Cannot save reference");
}

int main(int argc, char **argv) {
  require(argc == 5, "projection_host INPUT WEIGHTS128 N OUTPUT_DIR");
  char *end;
  unsigned long parsed = strtoul(argv[3], &end, 10);
  require(*argv[3] && !*end && parsed >= 32 && parsed <= MAX_N && parsed % 32 == 0,
          "N must be a multiple of 32 in 32..128");
  const unsigned n = (unsigned)parsed;
  float input[M*K], expected[M*MAX_N], check[M*MAX_N];
  unsigned char weights[MAX_N*KB*144], r4[MAX_N*KB*144];
  unsigned char row_q8[AB], packed[AB];
  const size_t wb = (size_t)n * KB * 144;
  _Static_assert(sizeof(qbs_block_q8_k_t) == 292, "Q8_K ABI");
  load(argv[1], input, sizeof(input));
  load(argv[2], weights, sizeof(weights));
  require(qbs_ref_quantize_q8_k(input, M*K, (qbs_block_q8_k_t *)row_q8, M*KB) == QBS_REF_OK,
          "Independent activation quantizer failed");
  require(qbs_ref_repack_weight_r4(QBS_WEIGHT_PROFILE_Q4_K, weights, wb, n, KB, r4, wb)
              == QBS_REF_OK, "Independent R4 pack failed");
  unsigned flags[2] = {0};
  for (unsigned mode = 0; mode < 2; ++mode) {
    const unsigned tm = mode ? 8 : 4;
    const unsigned tn = mode ? 16 : 32;
    for (unsigned row = 0; row < M; row += tm) {
      const void *a = row_q8 + (size_t)row*KB*292;
      if (mode)
        require(qbs_ref_pack_activation_m8_profile(QBS_ACTIVATION_PROFILE_Q8_K,
                a, tm*KB*292, tm, KB, packed, sizeof(packed)) == QBS_REF_OK,
                "Independent M8 pack failed");
      else
        require(qbs_ref_pack_activation_m4_profile(QBS_ACTIVATION_PROFILE_Q8_K,
                a, tm*KB*292, KB, packed, sizeof(packed)) == QBS_REF_OK,
                "Independent M4 pack failed");
      for (unsigned col = 0; col < n; col += tn) {
        const qbs_descriptor_fields_t fields = {
          .descriptor_version = QBS_DESCRIPTOR_VERSION,
          .weight_profile = QBS_WEIGHT_PROFILE_Q4_K,
          .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
          .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
          .activation_layout = mode ? QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED
                                    : QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED,
          .n = tn, .k_blocks = KB,
        };
        const qbs_descriptor_t descriptor = {
          .header = qbs_pack_descriptor_header(&fields), .weight_base = 0x81000000,
        };
        float result[256] = {0};
        qbs_ref_result_t info;
        require(qbs_ref_execute(&descriptor, tm, 8, 1024, 0x82000000,
                r4 + (size_t)col*KB*144, tn*KB*144, packed, tm*KB*292,
                result, 256, NULL, NULL, &info) == QBS_REF_OK,
                "Independent command failed");
        flags[mode] |= info.fflags;
        for (unsigned r = 0; r < tm; ++r)
          for (unsigned c = 0; c < tn; ++c)
            (mode ? check : expected)[(row+r)*n + col+c] = result[r*32+c];
      }
    }
  }
  require(flags[0] == flags[1] && !memcmp(expected, check, M*n*sizeof(float)),
          "M4/M8 output or exception oracle disagreement");
  save(argv[4], "input_f32.bin", input, sizeof(input));
  save(argv[4], "weights_r4.bin", r4, wb);
  save(argv[4], "expected_q8.bin", row_q8, sizeof(row_q8));
  save(argv[4], "expected.bin", expected, M*n*sizeof(float));
  save(argv[4], "flags.bin", flags, sizeof(unsigned));
  printf("STAGE2_PROJECTION_ORACLE_PASS m=8 k=2048 n=%u outputs=%u flags=%u ggml_golden=0\n",
         n, M*n, flags[0]);
  return 0;
}
