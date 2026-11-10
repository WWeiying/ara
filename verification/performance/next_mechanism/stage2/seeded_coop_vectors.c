#define main existing_command_vectors_main
#include "../../../qbs/qbs_command_vectors.c"
#undef main

enum { Rows = 8, Columns = 16, Blocks = 7 };
static qbs_block_q4_k_t weights[Columns][Blocks];
static qbs_block_q8_k_t activations[Rows][Blocks];

static void need(int ok) {
  if (!ok) { fputs("SEEDED_ORACLE_FAIL\n", stderr); exit(1); }
}

static void region(unsigned start, unsigned kb, unsigned char *w, unsigned char *a) {
  qbs_block_q4_k_t row_w[Columns * Blocks];
  qbs_block_q8_k_t row_a[Rows * Blocks];
  for (unsigned r = 0; r < Columns; r++)
    for (unsigned k = 0; k < kb; k++) row_w[r*kb+k] = weights[r][start+k];
  for (unsigned r = 0; r < Rows; r++)
    for (unsigned k = 0; k < kb; k++) row_a[r*kb+k] = activations[r][start+k];
  need(qbs_ref_repack_weight_r4(QBS_WEIGHT_PROFILE_Q4_K, row_w, Columns*kb*144,
       Columns, kb, w, Columns*kb*144) == QBS_REF_OK);
  need(qbs_ref_pack_activation_m8_profile(QBS_ACTIVATION_PROFILE_Q8_K,
       row_a, Rows*kb*292, Rows, kb, a, Rows*kb*292) == QBS_REF_OK);
}

static unsigned reference(unsigned start, unsigned kb, float *destination) {
  unsigned char w[Columns*Blocks*144], a[Rows*Blocks*292];
  region(start, kb, w, a);
  qbs_descriptor_fields_t f = {.descriptor_version=QBS_DESCRIPTOR_VERSION,
      .weight_profile=QBS_WEIGHT_PROFILE_Q4_K, .activation_profile=QBS_ACTIVATION_PROFILE_Q8_K,
      .weight_layout=QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
      .activation_layout=QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED, .n=Columns, .k_blocks=kb};
  qbs_descriptor_t d = {.header=qbs_pack_descriptor_header(&f), .weight_base=0x100000};
  qbs_ref_result_t result;
  memset(destination, 0, Rows*32*sizeof(float));
  need(qbs_ref_execute(&d, Rows, 8, 1024, 0x200000, w, Columns*kb*144,
       a, Rows*kb*292, destination, Rows*32, NULL, NULL, &result) == QBS_REF_OK);
  return result.fflags;
}

static void bytes(FILE *f, uint64_t base, const unsigned char *data, unsigned size) {
  for (unsigned offset = 0; offset < size; offset += 16) {
    fprintf(f, "B %016" PRIx64 " %04x ", base+offset, 0xffff);
    for (int b = 15; b >= 0; b--) fprintf(f, "%02x", data[offset+b]);
    fputc('\n', f);
  }
}

int main(int argc, char **argv) {
  need(argc == 2);
  for (unsigned r = 0; r < Columns; r++) for (unsigned k = 0; k < Blocks; k++) {
    fill_q4(&weights[r][k], r, k);
    if (k == 0) {
      weights[r][k].d = 0x3800; weights[r][k].dmin = 0x3400;
      for (unsigned i = 0; i < 12; i++) weights[r][k].scales[i] = i < 8 ? 1 : 0x11;
    }
  }
  for (unsigned r = 0; r < Rows; r++) for (unsigned k = 0; k < Blocks; k++) {
    fill_activation(&activations[r][k], r, k);
    if (k == 0) activations[r][k].d = (float)(r+1)*0.03125f;
  }
  FILE *f = fopen(argv[1], "wx"); need(f != NULL);
  fputs("S2SEED1\n", f);
  for (unsigned model = 0; model < 4; model++) {
    float result[Rows*32];
    unsigned flags = reference(0, 1+2*model, result);
    need(flags == (model ? 1u : 0u));
    fprintf(f, "F %u %u\n", model, flags);
    for (unsigned r = 0; r < Rows; r++) for (unsigned c = 0; c < Columns; c++) {
      uint32_t bits; memcpy(&bits, &result[r*32+c], sizeof(bits));
      need(isfinite(result[r*32+c]) && result[r*32+c] != 0.0f);
      fprintf(f, "O %u %u %08" PRIx32 "\n", model, r*16+c, bits);
    }
  }
  // The five regions contain prefix, three successive suffixes, and a late-fault payload.
  const unsigned starts[5] = {0,1,3,5,1}, depths[5] = {1,2,2,2,3};
  for (unsigned i = 0; i < 5; i++) {
    unsigned kb = depths[i];
    unsigned char w[Columns*Blocks*144], a[Rows*Blocks*292];
    uint64_t wb = 0x100000 + i*0x10000, ab = 0x200000 + i*0x10000;
    region(starts[i], kb, w, a);
    fprintf(f, "R %u %016" PRIx64 " %016" PRIx64 " %u\n", i, wb, ab, kb);
    bytes(f, wb, w, Columns*kb*144); bytes(f, ab, a, Rows*kb*292);
  }
  fputs("END\n", f); need(fclose(f) == 0);
  puts("SEEDED_ORACLE_PASS models=4 regions=5 nonzero_seeds=128 prefix_flags=0 continuation_flags=1");
  return 0;
}
