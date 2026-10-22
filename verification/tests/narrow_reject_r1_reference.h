// SPDX-License-Identifier: SHL-0.51
#ifndef NARROW_REJECT_R1_REFERENCE_H
#define NARROW_REJECT_R1_REFERENCE_H
#include <stdint.h>
#define R1_CASES 24
#define R1_PHASES 26
#define R1_CHECKS 15489
#define R1_REGS(X) X(0) X(1) X(2) X(3) X(4) X(5) X(6) X(7) \
  X(8) X(9) X(10) X(11) X(12) X(13) X(14) X(15) \
  X(16) X(17) X(18) X(19) X(20) X(21) X(22) X(23) \
  X(24) X(25) X(26) X(27) X(28) X(29) X(30) X(31)
#define R1_MATRIX(X) \
  X(00,"e64, m1",24,0xb28c0857) X(01,"e8, m1",0,0xb29c0857) \
  X(02,"e8, m2",1,0xb2ac0857) X(03,"e8, m4",2,0xb2cc0857) \
  X(04,"e64, m1",24,0xb283c857) X(05,"e8, m1",0,0xb293c857) \
  X(06,"e8, m2",1,0xb2a3c857) X(07,"e8, m4",2,0xb2c3c857) \
  X(08,"e64, m1",24,0xb280b857) X(09,"e8, m1",0,0xb290b857) \
  X(10,"e8, m2",1,0xb2a0b857) X(11,"e8, m4",2,0xb2c0b857) \
  X(12,"e64, m1",24,0xb68c0857) X(13,"e8, m1",0,0xb69c0857) \
  X(14,"e8, m2",1,0xb6ac0857) X(15,"e8, m4",2,0xb6cc0857) \
  X(16,"e64, m1",24,0xb683c857) X(17,"e8, m1",0,0xb693c857) \
  X(18,"e8, m2",1,0xb6a3c857) X(19,"e8, m4",2,0xb6c3c857) \
  X(20,"e64, m1",24,0xb680b857) X(21,"e8, m1",0,0xb690b857) \
  X(22,"e8, m2",1,0xb6a0b857) X(23,"e8, m4",2,0xb6c0b857)
static inline uint8_t r1_seed(unsigned r, unsigned i) {
  return (uint8_t)(r * 29 + i * 13 + ((i >> 3) ^ r) * 7 + 0x35);
}
static inline uint64_t r1_dump_word(unsigned phase, unsigned r, unsigned w) {
  if (w == 0 || w == 17) return UINT64_C(0xa5a5a5a5a5a5a5a5);
  uint64_t value = 0;
  for (unsigned b = 0; b < 8; ++b) {
    unsigned i = (w - 1) * 8 + b;
    uint8_t byte = r1_seed(r, i);
    if (phase == 25 && r == 16 && i < 4) byte = (uint8_t)(r1_seed(8, i) + 1);
    value |= (uint64_t)byte << (8 * b);
  }
  return value;
}
#endif
