#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "qbs/qbs.h"
#include "qbs_ref.h"
#include "config.h"

enum { M = EVAL_M, N = EVAL_N, K = 2048, KB = 8,
       AB = M*KB*292, WB = N*KB*EVAL_WB };

static void require(int ok, const char *s) {
  if (!ok) { fprintf(stderr, "%s\n", s); exit(1); }
}
static void load(const char *path, void *p, size_t n) {
  FILE *f = fopen(path, "rb");
  require(f && fread(p, 1, n, f) == n && fgetc(f) == EOF, "Input size/read error");
  require(!fclose(f), "Input close error");
}
static void save(const char *dir, const char *name, const void *p, size_t n) {
  char path[4096];
  require(snprintf(path, sizeof(path), "%s/%s", dir, name) < (int)sizeof(path), "Path too long");
  FILE *f = fopen(path, "wb");
  require(f && fwrite(p, 1, n, f) == n && !fclose(f), "Output error");
}
static uint64_t info(void *opaque, unsigned index) {
  (void)opaque;
  return qbs_ref_capability_word(index, 1024);
}

int main(int argc, char **argv) {
  require(argc == 4, "oracle INPUT WEIGHTS OUTPUT_DIR");
  float input[M*K], expected[M*N];
  unsigned char weights[WB], r4[WB], row[AB], packed[AB], sdk_pack[AB];
  unsigned seen[M*N] = {0}, flags = 0, count = 0;
  load(argv[1], input, sizeof(input)); load(argv[2], weights, WB);
  require(qbs_ref_quantize_q8_k(input, M*K, (qbs_block_q8_k_t *)row, M*KB) == QBS_REF_OK,
          "Independent quantizer failed");
  require(qbs_ref_repack_weight_r4(EVAL_PROFILE, weights, WB, N, KB, r4, WB) == QBS_REF_OK,
          "Independent R4 pack failed");
  if (EVAL_TILE == 8) {
    require(qbs_ref_pack_activation_m8_profile(1, row, AB, M, KB, packed, AB) == QBS_REF_OK,
            "Independent M8 pack failed");
    require(qbs_pack_activation_m8_grouped(1, row, AB, M, KB, sdk_pack, AB) == QBS_STATUS_OK,
            "SDK M8 pack failed");
  } else if (EVAL_TILE == 4) {
    for (unsigned r = 0; r < M; r += 4) {
      require(qbs_ref_pack_activation_m4_profile(1, row+r*KB*292, 4*KB*292, KB,
              packed+r*KB*292, 4*KB*292) == QBS_REF_OK, "Independent M4 pack failed");
      require(qbs_pack_activation_m4(1, row+r*KB*292, 4*KB*292, KB,
              sdk_pack+r*KB*292, 4*KB*292) == QBS_STATUS_OK, "SDK M4 pack failed");
    }
  } else { memcpy(packed, row, AB); memcpy(sdk_pack, row, AB); }
  require(!memcmp(packed, sdk_pack, AB), "SDK/reference packing disagreement");
  qbs_device_t device;
  qbs_plan_t plan;
  qbs_problem_t problem = {.weight_profile=EVAL_PROFILE, .activation_profile=1,
    .weight_layout=2, .activation_storage=EVAL_STORAGE, .m=M, .n=N, .k_elements=K};
  require(qbs_device_query(info, NULL, &device) == QBS_STATUS_OK &&
          qbs_plan_create(&device, &problem, &plan) == QBS_STATUS_OK, "SDK planner failed");
  require(!plan.split_k && !plan.needs_activation_gather && !plan.workspace_bytes,
          "Unexpected split/gather/workspace");
  printf("{\"context_eligible\":%u,\"commands\":[", !!qbs_plan_supports_activation_context(&plan));
  qbs_plan_cursor_t cursor;
  qbs_plan_cursor_reset(&cursor);
  for (;;) {
    qbs_command_t c;
    int has;
    require(qbs_plan_next(&plan, &cursor, &c, &has) == QBS_STATUS_OK, "Cursor failed");
    if (!has) break;
    require(c.k_blocks == KB && !c.k_block_start && !c.accumulate && !c.gather_activation,
            "Not full-K direct plan");
    qbs_descriptor_fields_t f = {.descriptor_version=QBS_DESCRIPTOR_VERSION,
      .weight_profile=EVAL_PROFILE, .activation_profile=1, .weight_layout=2,
      .activation_layout=c.activation_layout, .n=c.n, .k_blocks=KB};
    qbs_descriptor_t d = {.header=qbs_pack_descriptor_header(&f), .weight_base=0x81000000};
    float result[256] = {0};
    qbs_ref_result_t ri;
    require(qbs_ref_execute(&d, c.m, 8, 1024, 0x82000000,
            r4+c.weight_offset_bytes, c.n*KB*EVAL_WB,
            packed+c.activation_offset_bytes, c.m*KB*292,
            result, 256, NULL, NULL, &ri) == QBS_REF_OK, "Independent command failed");
    flags |= ri.fflags;
    for (unsigned r = 0; r < c.m; ++r)
      for (unsigned n = 0; n < c.n; ++n) {
        unsigned index = (c.input_start+r)*N+c.output_start+n;
        require(index < M*N && !seen[index]++, "Duplicate/out-of-bounds planned output");
        expected[index] = result[r*32+n];
      }
    printf("%s{\"m\":%u,\"n\":%u,\"row\":%u,\"col\":%u,\"layout\":%u}",
           count ? "," : "", c.m, c.n, c.input_start, c.output_start, c.activation_layout);
    ++count;
  }
  for (unsigned i = 0; i < M*N; ++i) require(seen[i] == 1, "Missing planned output");
  printf("],\"flags\":%u,\"outputs\":%u}\n", flags, M*N);
  save(argv[3], "weights_r4.bin", r4, WB);
  save(argv[3], "expected_q8.bin", row, AB);
  save(argv[3], "expected_packed.bin", packed, AB);
  save(argv[3], "expected.bin", expected, sizeof(expected));
  return 0;
}
