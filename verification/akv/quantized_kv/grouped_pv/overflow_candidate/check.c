#include "stride_check.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>

__attribute__((noinline)) int candidate(size_t stride, size_t factor, size_t limit) {
  return akv_pv_stride_exceeds(stride, factor, limit);
}

#ifndef ASSEMBLY_ONLY
static unsigned long checks;
static void check(size_t stride, size_t factor, size_t limit) {
  const int expected = factor && stride > limit / factor;
  assert(candidate(stride, factor, limit) == expected);
  ++checks;
}

int main(void) {
  for (size_t dim = 32; dim <= 256; ++dim) {
    size_t limit = SIZE_MAX / sizeof(float) - dim;
    for (size_t heads = 1; heads <= 8; ++heads) {
      size_t factor = heads - 1;
      size_t bound = factor ? limit / factor : SIZE_MAX;
      check(0, factor, limit);
      check(dim, factor, limit);
      check(SIZE_MAX, factor, limit);
      check(bound, factor, limit);
      if (bound) check(bound - 1, factor, limit);
      if (bound != SIZE_MAX) check(bound + 1, factor, limit);
    }
  }
  uint64_t state = UINT64_C(0x4d595df4d0f33173);
  for (unsigned i = 0; i < 1000000; ++i) {
    state = state * UINT64_C(6364136223846793005) + 1;
    size_t stride = (size_t)state;
    state = state * UINT64_C(6364136223846793005) + 1;
    size_t limit = (size_t)state;
    check(stride, i % 8, limit);
  }
  printf("STRIDE_EQUIVALENCE_PASS checks=%lu size_bits=%zu\n", checks, sizeof(size_t)*8);
  return 0;
}
#endif
