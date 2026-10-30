#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "hex32.h"

void _putchar(char character) {
  (void)putchar((unsigned char)character);
}

static void emit(uint32_t value, int reference) {
  if (reference) (void)printf("%08x", (unsigned)value);
  else fast_hex32(value);
}

int main(int argc, char **argv) {
  if (argc != 2 || (strcmp(argv[1], "reference") && strcmp(argv[1], "candidate"))) return 2;
  const int reference = !strcmp(argv[1], "reference");
  const uint32_t boundary[] = {
      0, 1, 15, 16, 255, 256, 4095, 4096, 65535, 65536,
      UINT32_C(0x7fffffff), UINT32_C(0x80000000), UINT32_C(0xfffffffe), UINT32_MAX,
      UINT32_C(0x01234567), UINT32_C(0x89abcdef), UINT32_C(0xaaaaaaaa), UINT32_C(0x55555555)};
  for (unsigned i = 0; i < sizeof(boundary)/sizeof(boundary[0]); ++i) emit(boundary[i], reference);
  for (uint32_t i = 0; i < 65536; ++i) emit(i, reference);
  for (uint32_t i = 0; i < 65536; ++i) emit(i << 16, reference);
  uint32_t state = UINT32_C(0x6d2b79f5);
  for (unsigned i = 0; i < 65536; ++i) {
    state ^= state << 13;
    state ^= state >> 17;
    state ^= state << 5;
    emit(state, reference);
  }
  return fflush(stdout) == 0 && !ferror(stdout) ? 0 : 3;
}
