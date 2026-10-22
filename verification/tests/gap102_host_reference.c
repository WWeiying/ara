#include <assert.h>
#include <stdio.h>
#include "gap102_reference.h"

int main(void) {
  assert(GAP102_VL == 129 && GAP102_CHECKS == 723);
  assert(gap102_accumulator(0) == UINT32_C(0x51000000));
  assert(gap102_accumulator(128) == UINT32_C(0x10251000));
  assert(gap102_after_word(192) == UINT64_C(0x106f104a10260180));
  assert(gap102_recovery_word(2) == UINT64_C(0xa5a5a5a551007000));
  for (unsigned offset = 0; offset < 4096; ++offset) {
    if (offset < 8 * 128 || offset >= 8 * 128 + 129 * 4)
      assert(gap102_after_byte(offset) == gap102_before_byte(offset));
  }
  puts("GAP102_HOST_REFERENCE_PASS full4096 prefix128 crossed129 no_storeoverflow");
  return 0;
}
