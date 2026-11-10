#define main matrix_original_vectors_main
#include "../../../qbs/qbs_command_vectors.c"
#undef main

int main(int argc, char **argv) {
  if (argc != 2) return 2;
  FILE *output = fopen(argv[1], "wx");
  if (output == NULL) return 2;
  fprintf(output, "QBSCMD1 1\n");
  int failed = emit_case(output, 0, QBS_WEIGHT_PROFILE_Q4_K,
                         QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                         QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED, 8, 4, 2);
  if (fclose(output) != 0) failed = 1;
  return failed ? 1 : 0;
}
