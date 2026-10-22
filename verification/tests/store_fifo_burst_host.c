// SPDX-License-Identifier: SHL-0.51
#include "store_fifo_burst_reference.h"
#include <stdio.h>
int main(void) {
  unsigned checks = 0;
  for (unsigned phase = 0; phase < 7; ++phase)
    for (unsigned store = 0; store < 8; ++store) {
      uint32_t memory[36];
      for (unsigned i = 0; i < 36; ++i) memory[i] = SFB_SENTINEL;
      for (unsigned i = 0; i < sfb_lengths[phase]; ++i)
        memory[i + 2] = UINT32_C(0x91e70031) ^ (i * UINT32_C(0x01030507));
      for (unsigned i = 0; i < 36; ++i) {
        if (memory[i] != sfb_expected(phase, i)) return 1;
        ++checks;
      }
    }
  if (checks != 2016) return 2;
  printf("HOST_STORE_MEMORY_MODEL_PASS checks=%u\n", checks);
  return 0;
}
