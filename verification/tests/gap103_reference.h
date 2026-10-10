#ifndef GAP103_REFERENCE_H
#define GAP103_REFERENCE_H
#include <stdint.h>

#define GAP103_VL 129
#define GAP103_VSTART 13
#define GAP103_CHECKS 1245

static uint32_t gap103_seed(unsigned i) {
  return UINT32_C(0x51a70329) + 131u * i;
}

static uint16_t gap103_shift(unsigned i) {
  return (uint16_t)(0x1200u | ((5u * i + 3u) & 31u));
}

static uint64_t gap103_guard(unsigned i) {
  return UINT64_C(0x9e37a5c35a6bd081) ^ (UINT64_C(0x0103070b11171d25) * i);
}

static uint8_t gap103_before_byte(unsigned offset) {
  if (offset >= 12*128 && offset < 16*128) {
    unsigned byte = offset - 12*128;
    return (uint8_t)(gap103_shift(byte/2) >> (8*(byte%2)));
  }
  if (offset >= 8*128 && offset < 16*128) {
    unsigned byte = offset - 8*128;
    return (uint8_t)(gap103_seed(byte/4) >> (8*(byte%4)));
  }
  return (uint8_t)(0x40u + offset/128);
}

static uint16_t gap103_output(unsigned i) {
  uint32_t wide = 0;
  uint16_t shift = 0;
  for (unsigned b = 0; b < 4; ++b)
    wide |= (uint32_t)gap103_before_byte(8*128+4*i+b) << (8*b);
  for (unsigned b = 0; b < 2; ++b)
    shift |= (uint16_t)gap103_before_byte(12*128+2*i+b) << (8*b);
  return (uint16_t)(wide >> (shift & 31u));
}

static uint8_t gap103_after_byte(unsigned offset) {
  if (offset >= 8*128+2*GAP103_VSTART && offset < 8*128+2*GAP103_VL) {
    unsigned byte = offset - 8*128;
    return (uint8_t)(gap103_output(byte/2) >> (8*(byte%2)));
  }
  return gap103_before_byte(offset);
}

static uint64_t gap103_image_word(unsigned word, unsigned after) {
  uint64_t value = 0;
  for (unsigned b = 0; b < 8; ++b)
    value |= (uint64_t)(after ? gap103_after_byte(word*8+b) :
                              gap103_before_byte(word*8+b)) << (8*b);
  return value;
}

static uint64_t gap103_seed_word(unsigned word) {
  if (word < 2) return gap103_guard(word);
  if (word >= 130) return gap103_guard(word-128);
  unsigned i = 2*(word-2);
  return (uint64_t)gap103_seed(i) | ((uint64_t)gap103_seed(i+1) << 32);
}

static uint64_t gap103_shift_word(unsigned word) {
  if (word < 2) return gap103_guard(word+4);
  if (word >= 66) return gap103_guard(word-60);
  uint64_t value = 0;
  for (unsigned b = 0; b < 4; ++b)
    value |= (uint64_t)gap103_shift(4*(word-2)+b) << (16*b);
  return value;
}

static uint64_t gap103_recovery_word(unsigned word) {
  uint64_t value = UINT64_C(0xa5a5a5a5a5a5a5a5);
  if (word == 2)
    value = (value & UINT64_C(0xffffffffffff0000)) |
            (uint16_t)gap103_image_word(8*16,1);
  return value;
}
#endif
