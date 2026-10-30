#include "../qbs_ref.h"

#include <fenv.h>
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { M = 4, N = 64, K = 8960, KB = 35, PN = 32, WB = 210,
       AB = 292, PACK = M * AB, WBYTES = N * KB * WB };
_Static_assert(sizeof(float) == 4 && FLT_RADIX == 2 && FLT_MANT_DIG == 24,
               "IEEE binary32 host required");
_Static_assert(sizeof(qbs_block_q6_k_t) == WB, "Q6_K layout");
_Static_assert(sizeof(qbs_block_q8_k_t) == AB, "Q8_K layout");

static const char *directory;

static void require(int ok, const char *message) {
  if (!ok) {
    fprintf(stderr, "PANEL_DATA_FAIL %s\n", message);
    exit(EXIT_FAILURE);
  }
}

static FILE *open_file(const char *name, const char *mode) {
  char path[4096];
  int size = snprintf(path, sizeof(path), "%s/%s", directory, name);
  require(size > 0 && (size_t)size < sizeof(path), "path length");
  FILE *file = fopen(path, mode);
  require(file != NULL, name);
  return file;
}

static void *read_file(const char *name, size_t bytes) {
  FILE *file = open_file(name, "rb");
  void *data = malloc(bytes);
  require(data != NULL, "allocation");
  require(fread(data, 1, bytes, file) == bytes && fgetc(file) == EOF,
          "input length");
  require(fclose(file) == 0, "input close");
  return data;
}

static void write_file(const char *name, const void *data, size_t bytes) {
  FILE *file = open_file(name, "wbx");
  require(fwrite(data, 1, bytes, file) == bytes, "output write");
  require(fclose(file) == 0, "output close");
}

static void repack(const uint8_t *row, unsigned blocks, uint8_t *r4) {
  size_t bytes = (size_t)PN * blocks * WB;
  require(qbs_ref_repack_weight_r4(QBS_WEIGHT_PROFILE_Q6_K, row, bytes,
                                 PN, blocks, r4, bytes) == QBS_REF_OK,
          "reference R4 repack");
}

static uint32_t oracle(const uint8_t *weight, const void *activation,
                       unsigned wlayout, unsigned alayout, float output[128]) {
  const qbs_descriptor_fields_t fields = {
      .descriptor_version = QBS_DESCRIPTOR_VERSION,
      .weight_profile = QBS_WEIGHT_PROFILE_Q6_K,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
      .weight_layout = (uint8_t)wlayout,
      .activation_layout = (uint8_t)alayout,
      .n = PN, .k_blocks = KB,
  };
  const qbs_descriptor_t descriptor = {
      .header = qbs_pack_descriptor_header(&fields), .weight_base = 0x1000,
  };
  qbs_ref_result_t result = {0};
  require(qbs_ref_execute(&descriptor, M, 8, 1024, 0x2000, weight,
                         PN * KB * WB, activation, M * KB * AB,
                         output, 128, NULL, NULL, &result) == QBS_REF_OK,
          "full-K reference execution");
  require(result.active_outputs == 128 && result.fflags <= 31,
          "oracle output work/flags");
  return result.fflags;
}

int main(int argc, char **argv) {
  require(argc == 2, "usage: generate OUTPUT_DIRECTORY");
  directory = argv[1];
  const uint32_t endian = 1;
  require(*(const uint8_t *)&endian == 1, "little endian host required");
  require(fesetenv(FE_DFL_ENV) == 0 && fesetround(FE_TONEAREST) == 0,
          "host floating-point environment");
  uint8_t *weights = read_file("weight_row.bin", WBYTES);
  float *activation = read_file("activation_f32.bin", M * K * sizeof(float));
  float *llama = read_file("llama_f32.bin", M * N * sizeof(float));
  for (unsigned i = 0; i < M * K; ++i)
    require(isfinite(activation[i]), "nonfinite captured activation");

  qbs_block_q8_k_t quant[M * KB];
  uint8_t packed[KB * PACK];
  require(qbs_ref_quantize_q8_k(activation, M * K, quant, M * KB) == QBS_REF_OK,
          "reference activation quantization");
  require(qbs_ref_pack_activation_m4_profile(QBS_ACTIVATION_PROFILE_Q8_K,
              quant, sizeof(quant), KB, packed, sizeof(packed)) == QBS_REF_OK,
          "reference activation packing");
  for (unsigned r = 0; r < M; ++r) {
    for (unsigned k = 0; k < KB; ++k) {
      const qbs_block_q8_k_t *q = &quant[r * KB + k];
      const uint8_t *p = packed + k * PACK;
      require(memcmp(p + 4 * r, &q->d, 4) == 0, "packed scale bytes");
      for (unsigned e = 0; e < 256; ++e)
        require(p[16 + 4 * e + r] == (uint8_t)q->qs[e], "packed quant bytes");
      for (unsigned g = 0; g < 16; ++g) {
        int sum = 0;
        for (unsigned e = 0; e < 16; ++e) sum += q->qs[g * 16 + e];
        require(sum == q->bsums[g], "Q8_K bsums");
        require(memcmp(p + 1040 + 2 * (g * 4 + r), &q->bsums[g], 2) == 0,
                "packed bsums bytes");
      }
    }
  }
  write_file("activation_q8k_row.bin", quant, sizeof(quant));
  write_file("activation_q8k_m4.bin", packed, sizeof(packed));

  uint8_t *full = malloc(WBYTES), *striped = malloc(WBYTES);
  uint8_t *reconstructed = malloc(WBYTES);
  uint8_t seen[N * KB] = {0};
  require(full != NULL && striped != NULL && reconstructed != NULL, "weight buffers");
  for (unsigned panel = 0; panel < 2; ++panel) {
    const unsigned base = panel * PN * KB * WB;
    repack(weights + base, KB, full + base);
    for (unsigned r = 0; r < PN; ++r)
      for (unsigned k = 0; k < KB; ++k)
        require(memcmp(full + base + ((r / 4 * KB + k) * 4 + r % 4) * WB,
                       weights + base + (r * KB + k) * WB, WB) == 0,
                "full R4 byte oracle");
    char name[64];
    snprintf(name, sizeof(name), "full_n%02u_r4.bin", panel * PN);
    write_file(name, full + base, PN * KB * WB);
  }
  unsigned cursor = 0, stripes = 0;
  for (unsigned k0 = 0; k0 < KB; k0 += 4, ++stripes) {
    unsigned blocks = KB - k0 < 4 ? KB - k0 : 4;
    size_t bytes = PN * blocks * WB;
    uint8_t gathered[PN * 4 * WB];
    for (unsigned panel = 0; panel < 2; ++panel) {
      for (unsigned r = 0; r < PN; ++r)
        memcpy(gathered + r * blocks * WB,
               weights + ((panel * PN + r) * KB + k0) * WB, blocks * WB);
      repack(gathered, blocks, striped + cursor);
      for (unsigned r = 0; r < PN; ++r) {
        for (unsigned k = 0; k < blocks; ++k) {
          unsigned logical = (panel * PN + r) * KB + k0 + k;
          const uint8_t *block = striped + cursor +
              ((r / 4 * blocks + k) * 4 + r % 4) * WB;
          require(!seen[logical]++, "duplicate stripe logical block");
          require(memcmp(block, weights + logical * WB, WB) == 0,
                  "stripe original every-byte comparison");
          memcpy(reconstructed + logical * WB, block, WB);
        }
      }
      char name[64];
      snprintf(name, sizeof(name), "stripe%02u_n%02u_r4.bin", stripes, panel * PN);
      write_file(name, striped + cursor, bytes);
      cursor += (unsigned)bytes;
    }
  }
  require(stripes == 9 && cursor == WBYTES, "stripe coverage size");
  for (unsigned i = 0; i < N * KB; ++i) require(seen[i] == 1, "stripe coverage");
  require(memcmp(weights, reconstructed, WBYTES) == 0, "stripe reconstruction");
  write_file("weight_full_r4.bin", full, WBYTES);
  write_file("weight_striped_r4.bin", striped, WBYTES);

  float expected[M * N], panel_output[2][128];
  uint32_t flags[2];
  for (unsigned panel = 0; panel < 2; ++panel) {
    float row_output[128];
    flags[panel] = oracle(full + panel * PN * KB * WB, packed,
                         QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                         QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED, panel_output[panel]);
    uint32_t row_flags = oracle(weights + panel * PN * KB * WB, quant,
                                QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                                QBS_ACTIVATION_LAYOUT_ROW_MAJOR, row_output);
    require(row_flags == flags[panel] &&
            memcmp(row_output, panel_output[panel], sizeof(row_output)) == 0,
            "independent row/R4 full-K oracle equivalence");
    for (unsigned r = 0; r < M; ++r)
      memcpy(expected + r * N + panel * PN, panel_output[panel] + r * PN,
             PN * sizeof(float));
  }
  write_file("expected_f32.bin", expected, sizeof(expected));
  write_file("expected_panel_f32.bin", panel_output, sizeof(panel_output));
  double max_abs = 0, max_rel = 0;
  unsigned mismatches = 0, bit_mismatches = 0;
  for (unsigned i = 0; i < M * N; ++i) {
    require(isfinite(expected[i]) && isfinite(llama[i]), "nonfinite output");
    double delta = fabs((double)expected[i] - llama[i]);
    double magnitude = fabs((double)llama[i]);
    double rel = delta / fmax(magnitude, 1e-30);
    if (delta > max_abs) max_abs = delta;
    if (rel > max_rel) max_rel = rel;
    mismatches += delta > 0.002 + 0.002 * magnitude;
    bit_mismatches += memcmp(&expected[i], &llama[i], sizeof(float)) != 0;
  }
  FILE *report = open_file("oracle.json", "wx");
  require(fprintf(report,
      "{\"state\":\"%s\",\"outputs\":256,\"panel_fflags\":[%u,%u],"
      "\"fflags\":%u,\"weight_bytes_checked\":%u,\"logical_blocks_checked\":%u,"
      "\"max_abs\":%.17g,\"max_rel\":%.17g,\"atol\":0.002,\"rtol\":0.002,"
      "\"llama_mismatches\":%u,\"llama_bit_mismatches\":%u}\n",
      mismatches ? "FAIL" : "PASS", flags[0], flags[1], flags[0] | flags[1],
      WBYTES, N * KB, max_abs, max_rel, mismatches, bit_mismatches) > 0,
      "report write");
  require(fclose(report) == 0, "report close");
  require(mismatches == 0, "captured llama tolerance");
  printf("PANEL_DATA_PASS outputs=256 weight_bytes=470400 stripes=9 fflags=%u\n",
         flags[0] | flags[1]);
  free(reconstructed); free(striped); free(full);
  free(llama); free(activation); free(weights);
  return EXIT_SUCCESS;
}
