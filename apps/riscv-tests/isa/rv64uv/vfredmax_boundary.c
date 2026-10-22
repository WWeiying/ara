// Focused regression for the VFREDMAX neutral-value / narrowing encoding
// collision. Keep this ELF independent from the broad legacy vfredmax test so
// a separate retirement failure cannot hide the reduction result.
#include "float_macros.h"
#include "vector_macros.h"

void TEST_CASE1(void) {
  VSET(4, e32, m1);
  VLOAD_32(v2, 0xC1700000, 0x41700000, 0x3F800000, 0xC0000000);
  VLOAD_32(v3, 0xFF800000);
  asm volatile("vfredmax.vs v1, v2, v3");
  VCMP_U32(1, v1, 0x41700000);

  VSET(1, e32, m1);
  VLOAD_32(v2, 0x41700000);
  VLOAD_32(v3, 0xFF800000);
  asm volatile("vfredmax.vs v1, v2, v3");
  VCMP_U32(2, v1, 0x41700000);
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  enable_fp();

  TEST_CASE1();
  EXIT_CHECK();
}
