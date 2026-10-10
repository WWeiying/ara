#include <stdint.h>
#include <stdio.h>
#include "gap104_reference.h"

int main(void) {
  const uint32_t words[2] = {0x42850407, 0x42850427};
  for (unsigned phase = 0; phase < 2; ++phase) {
    uint32_t word = words[phase];
    if ((word >> 29) != 2 || ((word >> 20) & 31) != 8 ||
        ((word >> 15) & 31) != 10 || ((word >> 7) & 31) != 8 ||
        ((word >> 12) & 7) != 0 || ((word >> 25) & 15) != 1 ||
        (word & 127) != (phase ? 0x27 : 0x07)) return 1;
    for (unsigned i = 0; i < 512; ++i) {
      uint64_t expected = 0;
      for (unsigned byte = 0; byte < 8; ++byte)
        expected |= (uint64_t)(0x40 + (i * 8 + byte) / 128) << (8 * byte);
      if (gap104_vrf_word(i) != expected) return 2;
    }
    for (unsigned i = 0; i < 64; ++i) {
      uint64_t expected = UINT64_C(0xa5a5a5a5a5a5a5a5);
      if (gap104_target_word(phase,i,0) != expected) return 3;
      if (i == 2) expected = (expected & ~UINT64_C(255)) | 0x48;
      if (gap104_target_word(phase,i,1) != expected) return 4;
    }
  }
  puts("GAP104_HOST_REFERENCE_PASS");
  return 0;
}
