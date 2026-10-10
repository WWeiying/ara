// SPDX-License-Identifier: SHL-0.51
#ifndef GAP104_REFERENCE_H
#define GAP104_REFERENCE_H
#include <stdint.h>

static inline uint64_t gap104_vrf_word(unsigned word) {
  return UINT64_C(0x0101010101010101) * (0x40 + word / 16);
}

static inline uint64_t gap104_target_word(unsigned phase, unsigned word, unsigned recovery) {
  (void)phase;
  return recovery && word == 2 ? UINT64_C(0xa5a5a5a5a5a5a548) : UINT64_C(0xa5a5a5a5a5a5a5a5);
}
#endif
