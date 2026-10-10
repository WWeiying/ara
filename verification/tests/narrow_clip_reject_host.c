// SPDX-License-Identifier: SHL-0.51
#include <stdio.h>
#include "narrow_clip_reject_reference.h"
struct cell { unsigned type, word; };
#define CELL(N,C,T,W) {T,W},
static const struct cell cells[] = { NC_MATRIX(CELL) };
#undef CELL
int main(void) {
  if (sizeof(cells)/sizeof(cells[0]) != 17 || NC_CHECKS != 2094) return 1;
  for (unsigned i = 0; i < 17; ++i) {
    unsigned w = cells[i].word, type = cells[i].type;
    unsigned sew = 8u << ((type >> 3) & 7), lm = 1u << (type & 7);
    unsigned src = (w >> 20) & 31, dest = (w >> 7) & 31;
    unsigned form = (w >> 12) & 7, rs1 = (w >> 15) & 31;
    if ((w & 127) != 87 || (w >> 26 != 46 && w >> 26 != 47) || !((w >> 25) & 1)) return 2;
    if (dest != 16 || dest % lm || dest + lm > 32) return 3;
    if ((form == 0 && (rs1 != 24 || rs1 % lm)) ||
        (form == 4 && rs1 != 7) || (form == 3 && rs1 != 1) ||
        (form != 0 && form != 3 && form != 4)) return 4;
    unsigned reasons = (sew > 32) + (lm > 4) + (lm <= 4 && src % (2 * lm) != 0);
    if (reasons != 1) return 5;
  }
  for (unsigned r = 0; r < 32; ++r)
    for (unsigned i = 0; i < 128; ++i) {
      unsigned independent = r * 36 + i * 13 + (((i >> 3) ^ r) - r) * 7 + 0x35;
      if (r1_seed(r,i) != (uint8_t)independent) return 6;
    }
  static const unsigned char recovery[] = {0x56,0x63,0x70,0x7d};
  for (unsigned i = 0; i < 4; ++i)
    if ((uint8_t)(r1_seed(8,i) + 1) != recovery[i]) return 7;
  puts("CLIP_HOST_PASS cases=17 checks=2094");
  return 0;
}
