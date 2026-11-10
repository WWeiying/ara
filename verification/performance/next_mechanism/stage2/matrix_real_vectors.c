#define main matrix_original_vectors_main
#include "../../../qbs/qbs_command_vectors.c"
#undef main

/* Same quantizer, ordered reference, flags and vector writer as the original.
 * A NULL capture golden explicitly omits the separate GGML error comparison. */
int main(int argc, char **argv) {
  unsigned full_n, k, input_start, m, output_start, n;
  if (argc != 9 || !parse_unsigned(argv[3], &full_n) ||
      !parse_unsigned(argv[4], &k) || !parse_unsigned(argv[5], &input_start) ||
      !parse_unsigned(argv[6], &m) || !parse_unsigned(argv[7], &output_start) ||
      !parse_unsigned(argv[8], &n) || (m != 4 && m != 8) || input_start > 8 ||
      m > 8 - input_start || full_n == 0 || full_n > 65536 || k == 0 ||
      k % QBS_BLOCK_ELEMENTS != 0 ||
      k / QBS_BLOCK_ELEMENTS > QBS_MAX_K_BLOCKS || n == 0 ||
      n > (m == 8 ? QBS_WIDE_M_MAX_N : QBS_MAX_N) ||
      output_start > full_n || n > full_n - output_start) {
    fprintf(stderr, "usage: %s OUTPUT DIRECTORY FULL_N K INPUT_START M OUTPUT_START N\n",
            argv[0]);
    return 2;
  }
  const unsigned blocks = k / QBS_BLOCK_ELEMENTS;
  const size_t row_bytes = (size_t)blocks * QBS_Q4_K_BLOCK_BYTES;
  const size_t weight_bytes = (size_t)n * row_bytes;
  const size_t activation_bytes = (size_t)m * k * sizeof(float);
  uint8_t *weights = malloc(weight_bytes);
  float *activations = malloc(activation_bytes);
  char path[4096];
  int ok = weights != NULL && activations != NULL;
  if (ok && snprintf(path, sizeof(path), "%s/weight_q4_K.bin", argv[2]) <
                (int)sizeof(path))
    ok = read_slice(path, (size_t)output_start * row_bytes, weights, weight_bytes);
  else
    ok = 0;
  if (ok && snprintf(path, sizeof(path), "%s/activation_f32.bin", argv[2]) <
                (int)sizeof(path))
    ok = read_slice(path, (size_t)input_start * k * sizeof(float), activations,
                    activation_bytes);
  else
    ok = 0;
  FILE *output = ok ? fopen(argv[1], "wx") : NULL;
  if (output == NULL) ok = 0;
  if (ok) {
    fprintf(output, "QBSCMD1 1\n");
    ok = emit_case_data(output, 0, QBS_WEIGHT_PROFILE_Q4_K,
                        QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                        m == 8 ? QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED
                               : QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED,
                        m, n, blocks, weights, activations, NULL) == 0;
  }
  if (output != NULL && fclose(output) != 0) ok = 0;
  free(activations);
  free(weights);
  if (!ok) {
    fprintf(stderr, "raw Q4_K reference generation failed (no synthetic fallback)\n");
    return 1;
  }
  fprintf(stderr, "STAGE2_RAW_REFERENCE golden=qbs_ref captured_golden=none "
                  "ggml_projection_check=0 M=%u N=%u K=%u input_start=%u output_start=%u\n",
          m, n, k, input_start, output_start);
  return 0;
}
