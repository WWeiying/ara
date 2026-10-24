#include <fenv.h>
#include <float.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* No host half arithmetic: construct the exact binary32 value of finite F16. */
static float half(uint16_t h) {
  uint32_t sign = (uint32_t)(h & 0x8000) << 16;
  uint32_t exponent = (h >> 10) & 31, mantissa = h & 1023, bits;
  if (exponent == 31) abort();
  if (exponent) bits = sign | ((exponent + 112) << 23) | (mantissa << 13);
  else if (!mantissa) bits = sign;
  else {
    int e = -14;
    while (!(mantissa & 1024)) { mantissa <<= 1; --e; }
    bits = sign | ((uint32_t)(e + 127) << 23) | ((mantissa & 1023) << 13);
  }
  float value;
  memcpy(&value, &bits, 4);
  return value;
}

static unsigned riscv_flags(int flags) {
  return ((flags & FE_INEXACT) ? 1u : 0u) |
         ((flags & FE_UNDERFLOW) ? 2u : 0u) |
         ((flags & FE_OVERFLOW) ? 4u : 0u) |
         ((flags & FE_DIVBYZERO) ? 8u : 0u) |
         ((flags & FE_INVALID) ? 16u : 0u);
}

static void read_exact(const char *name, void *data, size_t size) {
  FILE *f = fopen(name, "rb");
  if (!f || fread(data, 1, size, f) != size || fgetc(f) != EOF || fclose(f)) abort();
}

int main(int argc, char **argv) {
  if (argc != 4 || sizeof(float) != 4 || FLT_RADIX != 2 || FLT_MANT_DIG != 24)
    return 1;
  const uint16_t endian = 1;
  if (*(const unsigned char *)&endian != 1 || fesetround(FE_TONEAREST)) return 2;
  static uint16_t q[12 * 128], k[2 * 256 * 128];
  static float qf[12 * 128], kf[2 * 256 * 128];
  read_exact(argv[1], q, sizeof(q));
  read_exact(argv[2], k, sizeof(k));
  for (unsigned i = 0; i < 12 * 128; ++i) qf[i] = half(q[i]);
  for (unsigned i = 0; i < 2 * 256 * 128; ++i) kf[i] = half(k[i]);
  FILE *out = fopen(argv[3], "wb");
  if (!out) return 3;
  const unsigned vl[4] = {1, 64, 7, 63};
  for (unsigned id = 0; id < 8; ++id) {
    const unsigned head = id / 4, shape = id % 4, tile = shape < 2 ? 0 : 64;
    uint32_t bits[6 * 64];
    for (unsigned i = 0; i < 6 * 64; ++i) bits[i] = UINT32_C(0xa5a5a5a5);
    if (feclearexcept(FE_ALL_EXCEPT)) return 4;
    for (unsigned row = 0; row < 6; ++row) {
      for (unsigned token = 0; token < vl[shape]; ++token) {
        float sum = 0.0f;
        for (unsigned d = 0; d < 128; ++d)
          sum = fmaf(qf[(head * 6 + row) * 128 + d],
                     kf[(head * 256 + tile + token) * 128 + d], sum);
        memcpy(&bits[row * 64 + token], &sum, 4);
      }
    }
    const unsigned flags = riscv_flags(fetestexcept(FE_ALL_EXCEPT));
    if (fwrite(bits, sizeof(bits), 1, out) != 1) return 5;
    printf("ORACLE case=%u kvhead=%u tile=%u vl=%u stride=%u outputs=%u fcsr=%u\n",
           id, head, tile, vl[shape], shape < 2 ? 320 : 256, 6 * vl[shape], flags);
  }
  return fclose(out) != 0;
}
