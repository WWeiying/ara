#include <stdio.h>
#include "gap101_reference.h"

int main(void) {
  const uint32_t words[2] = {0xe2050827u, 0x22050fa7u};
  for (unsigned phase = 0; phase < 2; ++phase) {
    uint32_t instruction = words[phase];
    unsigned nf = (instruction >> 29) + 1;
    unsigned reg = (instruction >> 7) & 31;
    unsigned emul = phase ? 1 : 2;
    if ((instruction & 127) != 0x27 || ((instruction >> 15) & 31) != 10 ||
        ((instruction >> 12) & 7) || !(instruction & (1u << 25)) ||
        (phase == 0 ? !(nf * emul > 8 && reg + nf * emul == 32)
                    : !(nf * emul == 2 && reg + nf * emul == 33))) return 1;
    for (unsigned i = 0; i < 512; ++i) {
      uint64_t value = gap101_vrf_word(i);
      for (unsigned j = 0; j < 8; ++j)
        if (((value >> (8 * j)) & 255) != 0x40 + i / 16) return 2;
    }
    for (unsigned i = 0; i < 8; ++i) {
      if (gap101_target_word(phase, i, 0) != UINT64_C(0xa5a5a5a5a5a5a5a5)) return 3;
      uint64_t expected = i == 2 ? (phase ? UINT64_C(0xa5a5a5a5a5a55f5e)
                                                        : UINT64_C(0xa5a5a5a5a5a55150))
                                : UINT64_C(0xa5a5a5a5a5a5a5a5);
      if (gap101_target_word(phase, i, 1) != expected) return 4;
    }
  }
  puts("GAP101_HOST_REFERENCE_PASS");
  return 0;
}
