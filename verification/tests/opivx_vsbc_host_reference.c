#include <stdio.h>
#include "opivx_vsbc_reference.h"

int main(void) {
  static const uint8_t wanted[4] = {253, 255, 252, 124};
  for (unsigned i = 0; i < 4; ++i)
    if (vsbc_expected(1, 2, i) != wanted[i]) return 1;
  for (unsigned p = 0; p < 2; ++p)
    for (unsigned r = 0; r < 3; ++r)
      for (unsigned i = 0; i < 128; ++i)
        if ((!p || r != 2 || i >= 4) &&
            vsbc_expected(p, r, i) != vsbc_seed(r, i)) return 2;
  if (vsbc_dump_word(1, 2, 1) != UINT64_C(0x5a5a5a5a7cfcfffd)) return 3;
  puts("HOST_REFERENCE_PASS recovery=fd,ff,fc,7c protected_bytes=768");
  return 0;
}
