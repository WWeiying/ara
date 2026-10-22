// SPDX-License-Identifier: SHL-0.51
#ifndef PURE_WAR_REFERENCE_H
#define PURE_WAR_REFERENCE_H
#include <stdint.h>
#define PWR_CHECKS 1765
#define PWR_REGS(M) M(0) M(1) M(2) M(3) M(4) M(5) M(6) M(7) \
  M(8) M(9) M(10) M(11) M(12) M(13) M(14) M(15) \
  M(16) M(17) M(18) M(19) M(20) M(21) M(22) M(23) \
  M(24) M(25) M(26) M(27) M(28) M(29) M(30) M(31)
static inline uint8_t pwr_source(unsigned i) { return (17 * i + 193) & 255; }
static inline uint8_t pwr_index(unsigned i) { return (29 * i + 7) & 127; }
static inline uint8_t pwr_base(unsigned i) { return (73 * i + 41) & 255; }
static inline uint8_t pwr_byte(unsigned phase, unsigned reg, unsigned b) {
  if (reg >= 8 && reg < 16) {
    unsigned i = (reg - 8) * 128 + b;
    return phase ? pwr_base(pwr_index(i)) : pwr_source(i);
  }
  if (reg >= 16 && reg < 24) return pwr_index((reg - 16) * 128 + b);
  if (phase && reg >= 24) return pwr_source((reg - 24) * 128 + b) / 3;
  return (reg * 29 + b * 13 + ((b >> 3) ^ reg) * 7 + 0x35) & 255;
}
static inline uint64_t pwr_word(unsigned phase, unsigned reg, unsigned w) {
  if (w == 0 || w == 17) return UINT64_C(0xa5a5a5a5a5a5a5a5);
  uint64_t result = 0;
  for (unsigned b = 0; b < 8; ++b)
    result |= (uint64_t)pwr_byte(phase, reg, (w - 1) * 8 + b) << (8 * b);
  return result;
}
static inline uint64_t pwr_base_word(unsigned w) {
  if (w == 0 || w == 17) return UINT64_C(0xa5a5a5a5a5a5a5a5);
  uint64_t result = 0;
  for (unsigned b = 0; b < 8; ++b)
    result |= (uint64_t)pwr_base((w - 1) * 8 + b) << (8 * b);
  return result;
}
#endif
