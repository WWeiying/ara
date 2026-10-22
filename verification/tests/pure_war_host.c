// SPDX-License-Identifier: SHL-0.51
#include <stdio.h>
#include "pure_war_reference.h"
int main(void) {
  unsigned checks = 0;
  for (unsigned phase = 0; phase < 2; ++phase)
    for (unsigned r = 0; r < 32; ++r)
      for (unsigned w = 0; w < 18; ++w) {
        uint64_t expected = UINT64_C(0xa5a5a5a5a5a5a5a5);
        if (w > 0 && w < 17) {
          expected = 0;
          for (unsigned b = 0; b < 8; ++b) {
            unsigned n = (w - 1) * 8 + b, v;
            if (r >= 8 && r < 16) {
              unsigned i = (r - 8) * 128 + n;
              v = phase ? (73 * ((29 * i + 7) % 128) + 41) % 256 : (17 * i + 193) % 256;
            } else if (r >= 16 && r < 24) v = (29 * ((r - 16) * 128 + n) + 7) % 128;
            else if (phase && r >= 24) v = ((17 * ((r - 24) * 128 + n) + 193) % 256) / 3;
            else v = (r * 29 + n * 13 + ((n / 8) ^ r) * 7 + 0x35) % 256;
            expected |= (uint64_t)v << (8 * b);
          }
        }
        if (pwr_word(phase, r, w) != expected) return 1;
        ++checks;
      }
  for (unsigned w = 0; w < 18; ++w) {
    uint64_t expected = UINT64_C(0xa5a5a5a5a5a5a5a5);
    if (w > 0 && w < 17) {
      expected = 0;
      for (unsigned b = 0; b < 8; ++b)
        expected |= (uint64_t)((73 * ((w - 1) * 8 + b) + 41) % 256) << (8 * b);
    }
    if (pwr_base_word(w) != expected) return 2;
    ++checks;
  }
  printf("PURE_WAR_HOST_PASS independent_words=%u fullVL=1024 divisor=3\n", checks);
  return 0;
}
