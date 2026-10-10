// SPDX-License-Identifier: SHL-0.51
#ifndef MEMORY_EMUL_R2_REFERENCE_H
#define MEMORY_EMUL_R2_REFERENCE_H
#include "narrow_reject_r1_reference.h"
#define R2_PHASES 7
#define R2_CHECKS 4229
#define R2_MATRIX(X) \
  X(00,"e64, mf8",1,UINT64_C(0x8000000000000000),0,0x02050407) \
  X(01,"e64, mf8",1,UINT64_C(0x8000000000000000),0,0x02050427) \
  X(02,"e8, m8",4,3,4,0x02057427)
static inline uint8_t r2_input_byte(unsigned which, unsigned i) {
  return (uint8_t)((which == 0 ? 0x20 : which == 1 ? 0x60 : 0xa0) +
                   i * (which == 0 ? 11 : which == 1 ? 7 : 3));
}
static inline uint8_t r2_vrf_byte(unsigned phase, unsigned reg, unsigned i) {
  uint8_t value = r1_seed(reg, i);
  if (reg == 8) {
    if (phase >= 2 && i < 32) value = r2_input_byte(1, i);
    else if (phase == 1 && i < 4) value = r2_input_byte(0, i);
    if (phase == 6 && i < 4) value = r2_input_byte(2, i);
  }
  return value;
}
static inline uint64_t r2_buffer_word(unsigned which, unsigned word, unsigned output) {
  if (word == 0 || word == 17) return UINT64_C(0xa5a5a5a5a5a5a5a5);
  uint64_t result = 0;
  for (unsigned b = 0; b < 8; ++b) {
    unsigned i = (word - 1) * 8 + b;
    uint8_t v = output && i >= (which == 1 ? 32 : 4) ? 0xcc : r2_input_byte(which, i);
    result |= (uint64_t)v << (8 * b);
  }
  return result;
}
#endif
