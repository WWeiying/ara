#ifndef OPIVX_VSBC_REFERENCE_H
#define OPIVX_VSBC_REFERENCE_H
#include <stdint.h>

#define VSBC_CHECKS 138u
#define VSBC_BAD_WORD UINT32_C(0x4883c057)

static inline uint8_t vsbc_seed(unsigned reg, unsigned i) {
  static const uint8_t first[4] = {0, 3, 255, 128};
  if (reg == 0) return i == 0 ? 10 : (uint8_t)(i * 7 + 0x65);
  if (reg == 1) return i < 4 ? first[i] : (uint8_t)(i * 19 + 0x31);
  return 0x5a;
}

static inline uint8_t vsbc_expected(unsigned phase, unsigned reg, unsigned i) {
  if (phase && reg == 2 && i < 4)
    return (uint8_t)(vsbc_seed(1, i) - 3 - ((10 >> i) & 1));
  return vsbc_seed(reg, i);
}

static inline uint64_t vsbc_dump_word(unsigned phase, unsigned reg, unsigned word) {
  if (word == 0 || word == 17) return UINT64_C(0xa5a5a5a5a5a5a5a5);
  uint64_t value = 0;
  for (unsigned i = 0; i < 8; ++i)
    value |= (uint64_t)vsbc_expected(phase, reg, (word - 1) * 8 + i) << (8 * i);
  return value;
}
#endif
