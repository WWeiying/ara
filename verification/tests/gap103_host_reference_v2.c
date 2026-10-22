#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "gap103_reference.h"

int main(void) {
  uint8_t before[4096], after[4096];
  for (unsigned i = 0; i < sizeof before; ++i) before[i] = (uint8_t)(0x40+i/128);
  for (unsigned i = 0; i < 256; ++i) {
    uint32_t seed = UINT32_C(0x51a70329)+131u*i;
    for (unsigned b = 0; b < 4; ++b) before[1024+4*i+b] = (uint8_t)(seed>>(8*b));
  }
  for (unsigned i = 0; i < 256; ++i) {
    uint16_t shift = (uint16_t)(0x1200u | ((5*i+3)&31u));
    before[1536+2*i] = (uint8_t)shift;
    before[1536+2*i+1] = (uint8_t)(shift>>8);
  }
  memcpy(after,before,sizeof after);
  for (unsigned i = 13; i < 129; ++i) {
    uint32_t wide = 0;
    for (unsigned b = 0; b < 4; ++b) wide |= (uint32_t)before[1024+4*i+b]<<(8*b);
    unsigned shift = (unsigned)before[1536+2*i] | ((unsigned)before[1536+2*i+1]<<8);
    uint16_t result = (uint16_t)(wide >> (shift&31));
    after[1024+2*i] = (uint8_t)result;
    after[1024+2*i+1] = (uint8_t)(result>>8);
  }
  for (unsigned i = 0; i < sizeof before; ++i) {
    assert(before[i] == gap103_before_byte(i));
    assert(after[i] == gap103_after_byte(i));
    if (i < 1050 || i >= 1282) assert(after[i] == before[i]);
  }
  for (unsigned w = 0; w < 512; ++w) {
    uint64_t a = 0, b = 0;
    for (unsigned j = 0; j < 8; ++j) {
      a |= (uint64_t)before[w*8+j]<<(8*j);
      b |= (uint64_t)after[w*8+j]<<(8*j);
    }
    assert(a == gap103_image_word(w,0) && b == gap103_image_word(w,1));
  }
  for (unsigned word = 0; word < 132; ++word) {
    uint64_t expected;
    if (word < 2 || word >= 130) {
      unsigned i = word < 2 ? word : word-128;
      expected = UINT64_C(0x9e37a5c35a6bd081) ^ (UINT64_C(0x0103070b11171d25)*i);
    } else {
      unsigned i = 2*(word-2);
      expected = (uint64_t)(UINT32_C(0x51a70329)+131u*i) |
                 ((uint64_t)(UINT32_C(0x51a70329)+131u*(i+1))<<32);
    }
    assert(gap103_seed_word(word) == expected);
  }
  for (unsigned word = 0; word < 68; ++word) {
    uint64_t expected = 0;
    if (word < 2 || word >= 66) {
      unsigned i = word < 2 ? word+4 : word-60;
      expected = UINT64_C(0x9e37a5c35a6bd081) ^ (UINT64_C(0x0103070b11171d25)*i);
    } else {
      for (unsigned b = 0; b < 4; ++b) {
        unsigned i = 4*(word-2)+b;
        expected |= (uint64_t)(0x1200u | ((5u*i+3u)&31u))<<(16*b);
      }
    }
    assert(gap103_shift_word(word) == expected);
  }
  assert(gap103_recovery_word(2) == UINT64_C(0xa5a5a5a5a5a50329));
  puts("GAP103_HOST_INDEPENDENT_CANONICAL_PASS before4096 after4096 vstart13 VL129 active232");
  return 0;
}

