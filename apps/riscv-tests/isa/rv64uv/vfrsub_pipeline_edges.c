// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

#include <stdint.h>

#include "float_macros.h"
#include "vector_macros.h"

static void test_conversion_followed_by_vfrsub(void) {
  VSET(7, e32, mf2);

  VLOAD_32(v11, 0x3f800000, 0x3f800000, 0x3f800000, 0x3f800000,
           0x3f800000, 0x3f800000, 0x3f800000);
  VLOAD_32(v9, 0x0003ffff, 0x7ff80000, 0x46bf3f9d, 0x00000c81,
           0xbf800000, 0x3f800000, 0x00000000);
  VLOAD_8(v0, 0x7f);

  uint64_t scalar_bits = UINT64_C(0x7ff8000000000000);
  double scalar;
  asm volatile("fmv.d.x %0, %1" : "=f"(scalar) : "r"(scalar_bits));

  asm volatile("vfcvt.x.f.v v4, v11, v0.t\n"
               "vfrsub.vf v26, v9, %0\n"
               :
               : "f"(scalar));

  VCMP_U32(1, v26, 0x7fc00000, 0x7fc00000, 0x7fc00000, 0x7fc00000,
           0x7fc00000, 0x7fc00000, 0x7fc00000);
}

int main(void) {
  enable_vec();
  enable_fp();

  test_conversion_followed_by_vfrsub();

  EXIT_CHECK();
}
