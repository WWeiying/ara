#ifndef GAP101_REFERENCE_H
#define GAP101_REFERENCE_H
#include <stdint.h>

static uint64_t gap101_vrf_word(unsigned word) {
  return UINT64_C(0x0101010101010101) * (0x40u + word / 16u);
}

static uint64_t gap101_target_word(unsigned phase, unsigned word, int recovery) {
  uint64_t result = 0;
  for (unsigned byte = 0; byte < 8; ++byte) {
    unsigned index = word * 8 + byte;
    unsigned value = 0xa5;
    if (recovery && index == 16) value = phase ? 0x5e : 0x50;
    if (recovery && index == 17) value = phase ? 0x5f : 0x51;
    result |= (uint64_t)value << (byte * 8);
  }
  return result;
}
#endif
