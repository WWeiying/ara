#include <stdio.h>
#include "vnclipu_reject_reference.h"
int main(void) {
  if (vcr_word(0, 8, 1) != UINT64_C(0x0001000100001234)) return 1;
  if ((uint32_t)vcr_word(2, 16, 1) != UINT32_C(0xffff1234)) return 2;
  for (unsigned p = 0; p < 3; ++p)
    for (unsigned r = 0; r < 32; ++r) {
      if (vcr_word(p, r, 0) != UINT64_C(0xa5a5a5a5a5a5a5a5) ||
          vcr_word(p, r, 17) != UINT64_C(0xa5a5a5a5a5a5a5a5)) return 3;
      for (unsigned b = 0; b < 128; ++b)
        if (!(p == 2 && r == 16 && b < 4) &&
            vcr_expected(p, r, b) != vcr_seed(r, b)) return 4;
    }
  puts("HOST_REFERENCE_PASS full32VRF snapshots3 traps1 recovery1234,ffff");
  return 0;
}
