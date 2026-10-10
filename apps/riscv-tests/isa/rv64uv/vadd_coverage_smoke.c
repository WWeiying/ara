// Short self-checking RVV ALU stimulus for instrumented code coverage.
#include "vector_macros.h"

void TEST_CASE1(void) {
  VSET(4, e32, m1);
  VLOAD_32(v1, 1, 2, 3, 4);
  VLOAD_32(v2, 10, 20, 30, 40);
  asm volatile("vadd.vv v3, v1, v2");
  VCMP_U32(1, v3, 11, 22, 33, 44);
  asm volatile("vadd.vi v4, v3, -1");
  VCMP_U32(2, v4, 10, 21, 32, 43);

  VSET(4, e8, m1);
  VLOAD_8(v1, 1, 2, 3, 4);
  VLOAD_8(v2, 10, 20, 30, 40);
  VLOAD_8(v0, 0x0a);
  VCLEAR(v3);
  asm volatile("vadd.vv v3, v1, v2, v0.t");
  VCMP_U8(3, v3, 0, 22, 0, 44);
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  TEST_CASE1();
  EXIT_CHECK();
}
