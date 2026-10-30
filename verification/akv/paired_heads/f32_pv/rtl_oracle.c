/* File adapter for the sealed independent scalar C oracle, not an ISA model. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern int f32_pv_oracle(const uint32_t *, const uint32_t *, const uint32_t *,
                         const uint16_t *, unsigned, unsigned, uint32_t *);

int main(int argc, char **argv) {
  if (argc != 3) return 1;
  FILE *input = fopen(argv[1], "rb"), *golden = fopen(argv[2], "wb");
  if (!input || !golden) return 2;
  const unsigned dims[] = {64, 96, 128}, tokens[] = {1, 63, 64};
  unsigned char *data = malloc(34880);
  if (!data) return 3;
  for (unsigned id = 0; id < 3; ++id) {
    if (fread(data, 1, 34880, input) != 34880) return 4;
    uint32_t output[256];
    memset(output, 0xa5, sizeof(output));
    int flags = f32_pv_oracle((const uint32_t *)(const void *)(data + 33280),
        (const uint32_t *)(const void *)(data + 33856),
        (const uint32_t *)(const void *)(data + 33792),
        (const uint16_t *)(const void *)(data + 16896), dims[id], tokens[id], output);
    if (flags < 0 || (flags & ~31) || fwrite(output, 1, 1024, golden) != 1024) return 5;
    printf("F32_ORACLE case=%u d=%u tokens=%u outputs=%u fcsr=%u\n",
           id, dims[id], tokens[id], 2 * dims[id], (unsigned)flags | 8u);
  }
  if (fgetc(input) != EOF || ferror(input)) return 6;
  free(data);
  if (fclose(input) || fclose(golden)) return 7;
  return 0;
}
