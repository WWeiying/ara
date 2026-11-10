#define main matrix_original_vectors_main
#include "../../../qbs/qbs_command_vectors.c"
#undef main

int main(int argc, char **argv) {
  static const char *names[6] = {
      "qnan", "snan", "positive_inf", "negative_inf", "signed_zero", "subnormal"};
  if (argc != 2) return 2;
  FILE *output = fopen(argv[1], "wx");
  if (output == NULL) return 2;
  fprintf(output, "QBSCMD1 6\n");
  int failed = 0;
  for (unsigned kind = 0; kind < 6 && !failed; ++kind) {
    qbs_block_q4_k_t weights[5][2];
    for (unsigned row = 0; row < 5; ++row) {
      for (unsigned kb = 0; kb < 2; ++kb) {
        qbs_block_q4_k_t *block = &weights[row][kb];
        fill_q4(block, row, kb);
        switch (kind) {
          case 0: block->d = UINT16_C(0x7e00); break;
          case 1: block->d = UINT16_C(0x7c01); break;
          case 2: block->d = UINT16_C(0x7c00); break;
          case 3: block->d = UINT16_C(0xfc00); break;
          case 4:
            block->d = (row + kb) % 2 ? UINT16_C(0x8000) : 0;
            block->dmin = (row + kb) % 2 ? 0 : UINT16_C(0x8000);
            break;
          default:
            block->d = (row + kb) % 2 ? UINT16_C(0x03ff) : UINT16_C(0x0001);
            block->dmin = (row + kb) % 2 ? UINT16_C(0x0002) : UINT16_C(0x03fe);
            break;
        }
      }
    }
    failed = emit_case_data(output, kind, QBS_WEIGHT_PROFILE_Q4_K,
                            QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                            QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED,
                            8, 5, 2, (const uint8_t *)weights, NULL, NULL);
    fprintf(stderr, "STAGE2_SPECIAL_ORACLE case=%u kind=%s M=8 N=5 Kb=2 "
                    "source_activation=fill_q8 captured_golden=none\n", kind, names[kind]);
  }
  if (fclose(output) != 0) failed = 1;
  return failed ? 1 : 0;
}
