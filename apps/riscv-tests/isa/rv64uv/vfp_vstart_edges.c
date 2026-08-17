// Directed restart coverage for floating-point arithmetic and conversions.
// Active operands are exactly representable; skipped elements deliberately
// contain exceptional values to verify destination and fflags preservation.

#include "float_macros.h"
#include "vector_macros.h"

static void test_masked_fp32_vstart(void) {
  VSET(14, e32, m2);
  VLOAD_32(v12, 0x7f800000, 0x7f800000, 0x7f800000, 0x7f800000,
           0x7f800000, 0x3f800000, 0x3f800000, 0x3f800000,
           0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000,
           0x3f800000, 0x3f800000);
  VLOAD_32(v16, 0xff800000, 0xff800000, 0xff800000, 0xff800000,
           0xff800000, 0x40000000, 0x40000000, 0x40000000,
           0x40000000, 0x40000000, 0x40000000, 0x40000000,
           0x40000000, 0x40000000);
  VLOAD_32(v8, 0x42c60000, 0x42c60000, 0x42c60000, 0x42c60000,
           0x42c60000, 0x42c60000, 0x42c60000, 0x42c60000,
           0x42c60000, 0x42c60000, 0x42c60000, 0x42c60000,
           0x42c60000, 0x42c60000);
  VLOAD_8(v0, 0xaa, 0xaa);
  CLEAR_FFLAGS;
  asm volatile(
      "li t1, 5\n"
      "csrw vstart, t1\n"
      "vfadd.vv v8, v12, v16, v0.t\n"
      ::: "t1");
  CHECK_FFLAGS(0);
  VCMP_U32(1, v8, 0x42c60000, 0x42c60000, 0x42c60000, 0x42c60000,
           0x42c60000, 0x40400000, 0x42c60000, 0x40400000,
           0x42c60000, 0x40400000, 0x42c60000, 0x40400000,
           0x42c60000, 0x40400000);
}

static void test_masked_fp64_vstart(void) {
  VSET(10, e64, m2);
  VLOAD_64(v12, 0x3ff0000000000000, 0x3ff0000000000000,
           0x3ff0000000000000, 0x3ff0000000000000,
           0x3ff0000000000000, 0x3ff0000000000000,
           0x3ff0000000000000, 0x3ff0000000000000,
           0x3ff0000000000000, 0x3ff0000000000000);
  VLOAD_64(v16, 0x4000000000000000, 0x4000000000000000,
           0x4000000000000000, 0x4000000000000000,
           0x4000000000000000, 0x4000000000000000,
           0x4000000000000000, 0x4000000000000000,
           0x4000000000000000, 0x4000000000000000);
  VLOAD_64(v8, 0x4058c00000000000, 0x4058c00000000000,
           0x4058c00000000000, 0x4058c00000000000,
           0x4058c00000000000, 0x4058c00000000000,
           0x4058c00000000000, 0x4058c00000000000,
           0x4058c00000000000, 0x4058c00000000000);
  VLOAD_8(v0, 0xaa, 0xaa);
  CLEAR_FFLAGS;
  asm volatile(
      "li t1, 3\n"
      "csrw vstart, t1\n"
      "vfadd.vv v8, v12, v16, v0.t\n"
      ::: "t1");
  CHECK_FFLAGS(0);
  VCMP_U64(2, v8, 0x4058c00000000000, 0x4058c00000000000,
           0x4058c00000000000, 0x4008000000000000,
           0x4058c00000000000, 0x4008000000000000,
           0x4058c00000000000, 0x4008000000000000,
           0x4058c00000000000, 0x4008000000000000);
}

static void test_unmasked_fp32_vstart(void) {
  VSET(9, e32, m1);
  VLOAD_32(v12, 0x7f800000, 0x7f800000, 0x7f800000, 0x3f800000,
           0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000);
  VLOAD_32(v16, 0xff800000, 0xff800000, 0xff800000, 0x40000000,
           0x40000000, 0x40000000, 0x40000000, 0x40000000, 0x40000000);
  VLOAD_32(v8, 0x42c60000, 0x42c60000, 0x42c60000, 0x42c60000,
           0x42c60000, 0x42c60000, 0x42c60000, 0x42c60000, 0x42c60000);
  CLEAR_FFLAGS;
  asm volatile(
      "li t1, 3\n"
      "csrw vstart, t1\n"
      "vfadd.vv v8, v12, v16\n"
      ::: "t1");
  CHECK_FFLAGS(0);
  VCMP_U32(3, v8, 0x42c60000, 0x42c60000, 0x42c60000, 0x40400000,
           0x40400000, 0x40400000, 0x40400000, 0x40400000, 0x40400000);
}

static void test_vfmul_vstart(void) {
  VSET(9, e32, m1);
  VLOAD_32(v12, 0x7f800000, 0x7f800000, 0x7f800000,
           0x40000000, 0x40000000, 0x40000000,
           0x40000000, 0x40000000, 0x40000000);
  VLOAD_32(v16, 0, 0, 0, 0x40400000, 0x40400000, 0x40400000,
           0x40400000, 0x40400000, 0x40400000);
  VLOAD_32(v8, 0x42c60000, 0x42c60000, 0x42c60000,
           0x42c60000, 0x42c60000, 0x42c60000,
           0x42c60000, 0x42c60000, 0x42c60000);
  CLEAR_FFLAGS;
  asm volatile("li t1, 3; csrw vstart, t1; vfmul.vv v8, v12, v16" ::: "t1");
  CHECK_FFLAGS(0);
  VCMP_U32(4, v8, 0x42c60000, 0x42c60000, 0x42c60000,
           0x40c00000, 0x40c00000, 0x40c00000,
           0x40c00000, 0x40c00000, 0x40c00000);
}

static void test_vfdiv_masked_vstart(void) {
  VSET(9, e64, m1);
  VLOAD_64(v12, 0, 0, 0, 0x4018000000000000, 0x4018000000000000,
           0x4018000000000000, 0x4018000000000000,
           0x4018000000000000, 0x4018000000000000);
  VLOAD_64(v16, 0, 0, 0, 0x4000000000000000, 0x4000000000000000,
           0x4000000000000000, 0x4000000000000000,
           0x4000000000000000, 0x4000000000000000);
  VLOAD_64(v8, 0x4058c00000000000, 0x4058c00000000000,
           0x4058c00000000000, 0x4058c00000000000,
           0x4058c00000000000, 0x4058c00000000000,
           0x4058c00000000000, 0x4058c00000000000,
           0x4058c00000000000);
  VLOAD_8(v0, 0xaa, 0xaa);
  CLEAR_FFLAGS;
  asm volatile("li t1, 3; csrw vstart, t1; vfdiv.vv v8, v12, v16, v0.t" ::: "t1");
  CHECK_FFLAGS(0);
  VCMP_U64(5, v8, 0x4058c00000000000, 0x4058c00000000000,
           0x4058c00000000000, 0x4008000000000000,
           0x4058c00000000000, 0x4008000000000000,
           0x4058c00000000000, 0x4008000000000000,
           0x4058c00000000000);
}

static void test_vfsqrt_vstart(void) {
  VSET(9, e32, m1);
  VLOAD_32(v12, 0xbf800000, 0xbf800000, 0xbf800000,
           0x40800000, 0x40800000, 0x40800000,
           0x40800000, 0x40800000, 0x40800000);
  VLOAD_32(v8, 0x42c60000, 0x42c60000, 0x42c60000,
           0x42c60000, 0x42c60000, 0x42c60000,
           0x42c60000, 0x42c60000, 0x42c60000);
  CLEAR_FFLAGS;
  asm volatile("li t1, 3; csrw vstart, t1; vfsqrt.v v8, v12" ::: "t1");
  CHECK_FFLAGS(0);
  VCMP_U32(6, v8, 0x42c60000, 0x42c60000, 0x42c60000,
           0x40000000, 0x40000000, 0x40000000,
           0x40000000, 0x40000000, 0x40000000);
}

static void test_vfcvt_vstart(void) {
  VSET(9, e32, m1);
  VLOAD_32(v12, 0x7f800001, 0x7f800001, 0x7f800001,
           0x40000000, 0x40000000, 0x40000000,
           0x40000000, 0x40000000, 0x40000000);
  VLOAD_32(v8, 0x55555555, 0x55555555, 0x55555555,
           0x55555555, 0x55555555, 0x55555555,
           0x55555555, 0x55555555, 0x55555555);
  CLEAR_FFLAGS;
  asm volatile("li t1, 3; csrw vstart, t1; vfcvt.x.f.v v8, v12" ::: "t1");
  CHECK_FFLAGS(0);
  VCMP_U32(7, v8, 0x55555555, 0x55555555, 0x55555555,
           2, 2, 2, 2, 2, 2);
}

static void test_vfwcvt_vstart(void) {
  VSET(9, e64, m2);
  VLOAD_64(v8, 0x4058c00000000000, 0x4058c00000000000,
           0x4058c00000000000, 0x4058c00000000000,
           0x4058c00000000000, 0x4058c00000000000,
           0x4058c00000000000, 0x4058c00000000000,
           0x4058c00000000000);
  VSET(9, e32, m1);
  VLOAD_32(v12, 0x7f800001, 0x7f800001, 0x7f800001,
           0x3fc00000, 0x3fc00000, 0x3fc00000,
           0x3fc00000, 0x3fc00000, 0x3fc00000);
  CLEAR_FFLAGS;
  asm volatile("li t1, 3; csrw vstart, t1; vfwcvt.f.f.v v8, v12" ::: "t1");
  CHECK_FFLAGS(0);
  VSET(9, e64, m2);
  VCMP_U64(8, v8, 0x4058c00000000000, 0x4058c00000000000,
           0x4058c00000000000, 0x3ff8000000000000,
           0x3ff8000000000000, 0x3ff8000000000000,
           0x3ff8000000000000, 0x3ff8000000000000,
           0x3ff8000000000000);
}

static void test_vfncvt_vstart(void) {
  VSET(9, e64, m2);
  VLOAD_64(v16, 0x7ff0000000000001, 0x7ff0000000000001,
           0x7ff0000000000001, 0x3ff8000000000000,
           0x3ff8000000000000, 0x3ff8000000000000,
           0x3ff8000000000000, 0x3ff8000000000000,
           0x3ff8000000000000);
  VSET(9, e32, m1);
  VLOAD_32(v8, 0x42c60000, 0x42c60000, 0x42c60000,
           0x42c60000, 0x42c60000, 0x42c60000,
           0x42c60000, 0x42c60000, 0x42c60000);
  CLEAR_FFLAGS;
  asm volatile("li t1, 3; csrw vstart, t1; vfncvt.f.f.w v8, v16" ::: "t1");
  CHECK_FFLAGS(0);
  VCMP_U32(9, v8, 0x42c60000, 0x42c60000, 0x42c60000,
           0x3fc00000, 0x3fc00000, 0x3fc00000,
           0x3fc00000, 0x3fc00000, 0x3fc00000);
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  enable_fp();
  test_masked_fp32_vstart();
  test_masked_fp64_vstart();
  test_unmasked_fp32_vstart();
  test_vfmul_vstart();
  test_vfdiv_masked_vstart();
  test_vfsqrt_vstart();
  test_vfcvt_vstart();
  test_vfwcvt_vstart();
  test_vfncvt_vstart();
  EXIT_CHECK();
}
