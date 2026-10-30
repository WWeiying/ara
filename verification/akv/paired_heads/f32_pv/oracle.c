/* Independent head-major scalar oracle. No AKV headers or candidate algorithm. */
#include <fenv.h>
#include <math.h>
#include <stdint.h>
#include <string.h>

#pragma STDC FENV_ACCESS ON

static float from_bits(uint32_t bits) {
  float value;
  memcpy(&value, &bits, sizeof(value));
  return value;
}

static uint32_t to_bits(float value) {
  uint32_t bits;
  memcpy(&bits, &value, sizeof(bits));
  /* RISC-V arithmetic produces canonical NaNs; host payload/sign may differ. */
  if ((bits & 0x7fffffffU) > 0x7f800000U) bits = 0x7fc00000U;
  return bits;
}

static float half_value(uint16_t bits) {
  const unsigned exponent = (bits >> 10) & 31U;
  const unsigned fraction = bits & 1023U;
  float value = exponent ? ldexpf((float)(1024U + fraction), (int)exponent - 25)
                         : ldexpf((float)fraction, -24);
  return (bits & 0x8000U) ? -value : value;
}

int f32_pv_oracle(const uint32_t *score, const uint32_t *initial,
                  const uint32_t *scale, const uint16_t *value,
                  unsigned dim, unsigned tokens, uint32_t *output) {
  if ((dim != 64 && dim != 96 && dim != 128) || tokens == 0 || tokens > 64)
    return -1;
  for (unsigned t = 0; t < tokens; ++t)
    for (unsigned d = 0; d < dim; ++d)
      if ((value[t * dim + d] & 0x7c00U) == 0x7c00U) return -2;
  if (fesetround(FE_TONEAREST) || feclearexcept(FE_ALL_EXCEPT)) return -3;
  for (unsigned h = 0; h < 2; ++h) {
    for (unsigned d = 0; d < dim; ++d) {
      volatile float scaled = from_bits(initial[h * dim + d]) * from_bits(scale[h]);
      float accumulator = scaled;
      for (unsigned t = 0; t < tokens; ++t)
        accumulator = fmaf(from_bits(score[h * 64 + t]), half_value(value[t * dim + d]), accumulator);
      output[h * dim + d] = to_bits(accumulator);
    }
  }
  int flags = fetestexcept(FE_ALL_EXCEPT);
  return ((flags & FE_INEXACT) ? 1 : 0) | ((flags & FE_UNDERFLOW) ? 2 : 0) |
         ((flags & FE_OVERFLOW) ? 4 : 0) | ((flags & FE_DIVBYZERO) ? 8 : 0) |
         ((flags & FE_INVALID) ? 16 : 0);
}
