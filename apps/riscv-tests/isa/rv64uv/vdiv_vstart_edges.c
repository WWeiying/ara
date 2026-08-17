// Directed restart and byte-enable coverage for integer divide/remainder.

#include "vector_macros.h"

#define SENTINEL8  0xa5
#define SENTINEL16 0xa5a5
#define SENTINEL32 0xa5a5a5a5
#define SENTINEL64 0xa5a5a5a5a5a5a5a5ULL

static void test_vremu_unmasked_vstart(void) {
  VSET(19, e8, m1);
  VLOAD_8(v8, SENTINEL8, SENTINEL8, SENTINEL8, SENTINEL8, SENTINEL8,
          SENTINEL8, SENTINEL8, SENTINEL8, SENTINEL8, SENTINEL8,
          SENTINEL8, SENTINEL8, SENTINEL8, SENTINEL8, SENTINEL8,
          SENTINEL8, SENTINEL8, SENTINEL8, SENTINEL8);
  VLOAD_8(v12, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21,
          23, 25, 27, 29, 31, 33, 35, 37, 39);
  asm volatile("li t0, 5; csrw vstart, t0; vremu.vv v8, v12, v12" ::: "t0");
  VCMP_U8(1, v8, SENTINEL8, SENTINEL8, SENTINEL8, SENTINEL8, SENTINEL8,
          0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
}

static void test_vrem_masked_vstart(void) {
  VSET(10, e16, m1);
  VLOAD_16(v8, SENTINEL16, SENTINEL16, SENTINEL16, SENTINEL16, SENTINEL16,
           SENTINEL16, SENTINEL16, SENTINEL16, SENTINEL16, SENTINEL16);
  VLOAD_16(v12, -21, -22, -23, -24, -25, -26, -27, -28, -29, -30);
  VLOAD_16(v16, -21, -22, -23, -24, -25, -26, -27, -28, -29, -30);
  VLOAD_8(v0, 0xaa, 0x02);
  asm volatile("li t0, 3; csrw vstart, t0; vrem.vv v8, v12, v16, v0.t" ::: "t0");
  VCMP_U16(2, v8, SENTINEL16, SENTINEL16, SENTINEL16, 0, SENTINEL16,
           0, SENTINEL16, 0, SENTINEL16, 0);
}

static void test_vdivu_vx_vstart(void) {
  VSET(9, e32, m1);
  VLOAD_32(v8, SENTINEL32, SENTINEL32, SENTINEL32, SENTINEL32, SENTINEL32,
           SENTINEL32, SENTINEL32, SENTINEL32, SENTINEL32);
  VLOAD_32(v12, 100, 104, 108, 112, 116, 120, 124, 128, 132);
  asm volatile("li t0, 2; csrw vstart, t0; li t1, 4; vdivu.vx v8, v12, t1"
               ::: "t0", "t1");
  VCMP_U32(3, v8, SENTINEL32, SENTINEL32, 27, 28, 29, 30, 31, 32, 33);
}

static void test_vdiv_vx_masked_vstart(void) {
  VSET(7, e64, m1);
  VLOAD_64(v8, SENTINEL64, SENTINEL64, SENTINEL64, SENTINEL64,
           SENTINEL64, SENTINEL64, SENTINEL64);
  VLOAD_64(v12, -30, -33, -36, -39, -42, -45, -48);
  VLOAD_8(v0, 0x55);
  asm volatile("li t0, 1; csrw vstart, t0; li t1, -3; vdiv.vx v8, v12, t1, v0.t"
               ::: "t0", "t1");
  VCMP_U64(4, v8, SENTINEL64, SENTINEL64, 12, SENTINEL64,
           14, SENTINEL64, 16);
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  test_vremu_unmasked_vstart();
  test_vrem_masked_vstart();
  test_vdivu_vx_vstart();
  test_vdiv_vx_masked_vstart();
  EXIT_CHECK();
}
