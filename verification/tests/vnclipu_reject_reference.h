#ifndef VNCLIPU_REJECT_REFERENCE_H
#define VNCLIPU_REJECT_REFERENCE_H
#include <stdint.h>
#define VCR_CHECKS 2346u
#define VCR_BAD_WORD UINT32_C(0xbaa04857)
#define VCR_REGS(M) M(0) M(1) M(2) M(3) M(4) M(5) M(6) M(7) \
  M(8) M(9) M(10) M(11) M(12) M(13) M(14) M(15) \
  M(16) M(17) M(18) M(19) M(20) M(21) M(22) M(23) \
  M(24) M(25) M(26) M(27) M(28) M(29) M(30) M(31)

static inline uint8_t vcr_seed(unsigned reg, unsigned byte) {
  static const uint8_t first[8] = {0x34, 0x12, 0, 0, 1, 0, 1, 0};
  if (reg == 8 && byte < 8) return first[byte];
  return (uint8_t)(reg * 29 + byte * 13 + ((byte >> 3) ^ reg) * 7 + 0x35);
}

static inline uint8_t vcr_expected(unsigned phase, unsigned reg, unsigned byte) {
  static const uint8_t recovery[4] = {0x34, 0x12, 0xff, 0xff};
  if (phase == 2 && reg == 16 && byte < 4) return recovery[byte];
  return vcr_seed(reg, byte);
}

static inline uint64_t vcr_word(unsigned phase, unsigned reg, unsigned word) {
  if (word == 0 || word == 17) return UINT64_C(0xa5a5a5a5a5a5a5a5);
  uint64_t value = 0;
  for (unsigned b = 0; b < 8; ++b)
    value |= (uint64_t)vcr_expected(phase, reg, (word - 1) * 8 + b) << (8 * b);
  return value;
}
#endif
