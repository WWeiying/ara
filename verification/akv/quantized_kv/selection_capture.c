#include "software/akv/experimental/quantized_kv/selection.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

static void *load(const char *path, size_t expected) {
  FILE *file = fopen(path, "rb");
  assert(file && fseek(file, 0, SEEK_END) == 0 && ftell(file) == (long)expected);
  rewind(file);
  void *data = malloc(expected);
  assert(data && fread(data, 1, expected, file) == expected && fclose(file) == 0);
  return data;
}

int main(int argc, char **argv) {
  assert(argc == 6 && (argv[1][0] == '0' || argv[1][0] == '1') && argv[1][1] == '\0');
  const unsigned q4 = argv[1][0] == '1';
  const size_t row = q4 ? 72 : 136;
  void *query = load(argv[2], 6144), *key = load(argv[3], 512*row);
  void *value = load(argv[4], 69632), *mask = load(argv[5], 512);
  void *output = malloc(6144);
  assert(output);
  memset(output, 0xa5, 6144);
  qbs_device_t device;
  assert(qbs_device_init_reference(1024, &device) == QBS_STATUS_OK);
  akv_quant_selection_input_t p = {
    .requested=1, .vlen_bits=1024, .normal_memory=1, .device=&device,
    .key_encoding=q4 ? QBS_WEIGHT_ENCODING_Q4_0 : QBS_WEIGHT_ENCODING_Q8_0_WEIGHT,
    .value_encoding=QBS_WEIGHT_ENCODING_Q8_0_WEIGHT,
    .query={query, 6144, 512, 512, 128, 1, 12},
    .key={key, 512*row, row, 256*row, 128, 256, 2},
    .value={value, 69632, 136, 34816, 128, 256, 2},
    .output={output, 6144, 512, 512, 128, 1, 12},
    .mask=mask, .mask_bytes=512,
  };
  const uint32_t scale = UINT32_C(0x3db504f3);
  memcpy(&p.scale, &scale, sizeof(scale));
  akv_quant_selection_t selection;
  assert(akv_quant_select(&p, &selection) == AKV_QUANT_SELECT_OK);
  assert(selection.group_heads == 6 && selection.kv_heads == 2 && selection.dim == 128 &&
         selection.visible_tokens == 128 && selection.key_row_bytes == row &&
         selection.query_quant_row_bytes == 136);
  for (unsigned i=0; i<6144; ++i) assert(((unsigned char *)output)[i] == 0xa5);
  printf("QUANT_CAPTURE_SELECTION_HOST_PASS q4=%u groups=6 kv_heads=2 d=128 visible=128 outputs_untouched=1 device=reference native_execution=0\n", q4);
  free(query); free(key); free(value); free(mask); free(output);
  return 0;
}
