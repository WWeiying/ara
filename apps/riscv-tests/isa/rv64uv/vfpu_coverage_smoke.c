// Short self-checking FP32 vector stimulus for instrumented code coverage.
#include "vector_macros.h"

static void test_fp32(void) {
  VSET(4, e32, m1);
  VLOAD_32(v1, 0x3f800000, 0x40000000, 0x40400000, 0x40800000);
  VLOAD_32(v2, 0x3f800000, 0x40000000, 0x40400000, 0x40800000);
  VLOAD_32(v3, 0x40000000, 0x40400000, 0x40800000, 0x40a00000);

  asm volatile("vfadd.vv v4, v2, v3");
  VCMP_U32(1, v4, 0x40400000, 0x40a00000, 0x40e00000, 0x41100000);

  asm volatile("vfmul.vv v5, v2, v3");
  VCMP_U32(2, v5, 0x40000000, 0x40c00000, 0x41400000, 0x41a00000);

  asm volatile("vfmacc.vv v1, v2, v3");
  VCMP_U32(3, v1, 0x40400000, 0x41000000, 0x41700000, 0x41c00000);

}

int main(void) {
  INIT_CHECK();
  enable_vec();
  enable_fp();
  test_fp32();
  EXIT_CHECK();
}
