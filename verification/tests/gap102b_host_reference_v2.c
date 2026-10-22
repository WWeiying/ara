#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "gap102b_reference.h"

int main(void) {
  uint8_t before[4096], after[4096];
  for (unsigned i = 0; i < 4096; ++i) before[i] = (uint8_t)(0x40 + i / 128);
  for (unsigned i = 0; i < 256; ++i) {
    uint32_t value = UINT32_C(0x51000000) + 131u * i;
    for (unsigned b = 0; b < 4; ++b) before[1024 + i * 4 + b] = (uint8_t)(value >> (b * 8));
  }
  const uint16_t source = (uint16_t)(0x1000u + 37u * 128u);
  before[1792] = (uint8_t)source;
  before[1793] = (uint8_t)(source >> 8);
  memcpy(after, before, sizeof after);
  uint32_t accumulator = 0;
  for (unsigned b = 0; b < 4; ++b) accumulator |= (uint32_t)before[1536 + b] << (b * 8);
  uint32_t result = accumulator + 7u * source;
  assert(accumulator == UINT32_C(0x51004180) && result == UINT32_C(0x51013300));
  for (unsigned b = 0; b < 4; ++b) after[1536 + b] = (uint8_t)(result >> (b * 8));
  for (unsigned i = 0; i < 4096; ++i) {
    assert(before[i] == gap102b_before_byte(i));
    assert(after[i] == gap102b_after_byte(i));
    if (i < 1536 || i >= 1540) assert(after[i] == before[i]);
  }
  for (unsigned word = 0; word < 512; ++word) {
    uint64_t value = 0;
    for (unsigned b = 0; b < 8; ++b) value |= (uint64_t)after[word * 8 + b] << (b * 8);
    assert(value == gap102b_after_word(word));
  }
  assert(gap102b_recovery_word(2) == UINT64_C(0xa5a5a5a551013300));
  puts("GAP102B_HOST_INDEPENDENT_REFERENCE_PASS full4096 source2 MAC4 vstart128");
  return 0;
}
