#ifndef GAP102B_REFERENCE_H
#define GAP102B_REFERENCE_H
#include <stdint.h>

#define GAP102B_VL 129
#define GAP102B_VSTART 128
#define GAP102B_CHECKS 723

static uint32_t gap102b_seed(unsigned i) {
  return UINT32_C(0x51000000) + 131u * i;
}

static uint16_t gap102b_source(unsigned i) {
  return (uint16_t)(0x1000u + 37u * i);
}

static uint8_t gap102b_before_byte(unsigned offset) {
  if (offset >= 12 * 128 + GAP102B_VSTART * 2 && offset < 12 * 128 + GAP102B_VL * 2) {
    unsigned source_byte = offset - 12 * 128;
    return (uint8_t)(gap102b_source(source_byte / 2) >> (8 * (source_byte % 2)));
  }
  if (offset >= 8 * 128 && offset < 16 * 128) {
    unsigned seed_byte = offset - 8 * 128;
    return (uint8_t)(gap102b_seed(seed_byte / 4) >> (8 * (seed_byte % 4)));
  }
  return (uint8_t)(0x40u + offset / 128);
}

static uint32_t gap102b_accumulator(unsigned i) {
  uint32_t value = 0;
  for (unsigned byte = 0; byte < 4; ++byte)
    value |= (uint32_t)gap102b_before_byte(8 * 128 + i * 4 + byte) << (byte * 8);
  return value;
}

static uint8_t gap102b_after_byte(unsigned offset) {
  if (offset >= 8 * 128 + GAP102B_VSTART * 4 && offset < 8 * 128 + GAP102B_VL * 4) {
    unsigned byte = offset - 8 * 128;
    unsigned element = byte / 4;
    uint32_t value = gap102b_accumulator(element) + 7u * (uint32_t)gap102b_source(element);
    return (uint8_t)(value >> (8 * (byte % 4)));
  }
  return gap102b_before_byte(offset);
}

static uint64_t gap102b_after_word(unsigned word) {
  uint64_t value = 0;
  for (unsigned byte = 0; byte < 8; ++byte)
    value |= (uint64_t)gap102b_after_byte(word * 8 + byte) << (8 * byte);
  return value;
}

static uint64_t gap102b_recovery_word(unsigned word) {
  uint64_t value = UINT64_C(0xa5a5a5a5a5a5a5a5);
  if (word == 2)
    value = (value & UINT64_C(0xffffffff00000000)) |
            (uint32_t)(gap102b_accumulator(128) + 7u * gap102b_source(128));
  return value;
}
#endif
