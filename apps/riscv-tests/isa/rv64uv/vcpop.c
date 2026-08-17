// Copyright 2021 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Author: Matheus Cavalcante <matheusd@iis.ee.ethz.ch>
//         Basile Bougenot <bbougenot@student.ethz.ch>

#include "vector_macros.h"

// masked
void TEST_CASE1(void) {
  VSET(4, e32, m1);
  VCLEAR(v2);
  VLOAD_32(v2, 7, 0, 0, 0);
  VLOAD_32(v0, 5, 0, 0, 0);
  volatile uint32_t scalar = 1337;
  volatile uint32_t OUP[] = {0, 0, 0, 0};
  asm volatile("vpopc.m %[A], v2, v0.t \n"
               "sw %[A], (%1) \n"
               :
               : [A] "r"(scalar), "r"(OUP));
  XCMP(1, OUP[0], 2);

  VSET(32, e32, m1);
  VLOAD_32(v8, 0xFFFFFFF7FFFFFFFF, 0x88, 0x1, 0x1F, 0xFFFFFFF7FFFFFFFF, 0x88,
           0x1, 0x1F, 0xFFFFFFF7FFFFFFFF, 0x88, 0x1, 0x1F, 0xFFFFFFF7FFFFFFFF,
           0x88, 0x1, 0x1F, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
  VLOAD_32(v0, 0xffffffffffffffff, 0xfffffffffffffff7, 0xffffffffffffffff,
           0xffffffffffffffff, 0xffffffffffffffff, 0xffffffffffffffff,
           0xffffffffffffffff, 0xffffffffffffffff, 0xffffffffffffffff,
           0xffffffffffffffff, 0xffffffffffffffff, 0xffffffffffffffff,
           0xffffffffffffffff, 0xffffffffffffffff, 0xffffffffffffffff,
           0xefffffffffffffff, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
  VSET(1024, e8, m8);
  asm volatile("vpopc.m %[A], v8, v0.t \n"
               "sw %[A], (%1) \n"
               :
               : [A] "r"(scalar), "r"(OUP));
  XCMP(2, OUP[0], 159);
}

// unmasked
void TEST_CASE2(void) {
  VSET(4, e32, m1);
  VLOAD_32(v2, 0xFFFFFFF7FFFFFFFF, 0x88, 0x1, 0x1F);
  volatile uint32_t scalar = 1337;
  volatile uint32_t OUP[] = {0, 0, 0, 0};
  VSET(128, e32, m2);
  asm volatile("vpopc.m %[A], v2 \n"
               "sw %[A], (%1) \n"
               :
               : [A] "r"(scalar), "r"(OUP));
  // VLEN=1024, SEW=32 and LMUL=2 cap vl at VLMAX=64. The first 64
  // mask bits contain 34 set bits; the requested AVL of 128 is not vl.
  XCMP(3, OUP[0], 34);

  VSET(8, e32, m1);
  VLOAD_32(v0, 0xFFFFFFF7FFFFFFFF, 0x88, 0x1, 0x1F, 0xFFFFFFF7FFFFFFFF, 0x88,
           0x1, 0x1F);
  VSET(256, e8, m8);
  asm volatile("vpopc.m %[A], v0 \n"
               "sw %[A], (%1) \n"
               :
               : [A] "r"(scalar), "r"(OUP));
  XCMP(4, OUP[0], 80);

  VSET(16, e32, m1);
  VLOAD_32(v0, 0xFFFFFFF7FFFFFFFF, 0x88, 0x1, 0x1F, 0xFFFFFFF7FFFFFFFF, 0x88,
           0x1, 0x1F, 0xFFFFFFF7FFFFFFFF, 0x88, 0x1, 0x1F, 0xFFFFFFF7FFFFFFFF,
           0x88, 0x1, 0x1F);
  VSET(1024, e8, m8);
  asm volatile("vpopc.m %[A], v0 \n"
               "sw %[A], (%1) \n"
               :
               : [A] "r"(scalar), "r"(OUP));
  XCMP(5, OUP[0], 160);

  VSET(8, e32, m1);
  VLOAD_32(v2, 0xFFFFFFF7FFFFFFFF, 0x88, 0x1, 0x1F, 0xFFFFFFF7FFFFFFFF, 0x88,
           0x1, 0x1F);
  VSET(256, e8, m1);
  asm volatile("vpopc.m %[A], v2 \n"
               "sw %[A], (%1) \n"
               :
               : [A] "r"(scalar), "r"(OUP));
  // With e8,m1, VLMAX is 128 rather than the requested AVL of 256.
  XCMP(6, OUP[0], 40);

  VSET(2, e32, m1);
  VLOAD_8(v2, 0xFF, 0x88);
  VSET(16, e16, m1);
  asm volatile("vcpop.m %[A], v2 \n"
               "sw %[A], (%1) \n"
               :
               : [A] "r"(scalar), "r"(OUP));
  XCMP(7, OUP[0], 10);

  VSET(4, e32, m1);
  VLOAD_32(v2, 0xF, 0, 0, 0);
  asm volatile("vpopc.m %[A], v2 \n"
               "sw %[A], (%1) \n"
               :
               : [A] "r"(scalar), "r"(OUP));
  XCMP(8, OUP[0], 4);

  // The final 16-bit popcount slice contains one tail bit. It must not
  // contribute even when the physical bit in the mask register is set.
  VSET(80, e8, m1);
  asm volatile("vmv.v.i v2, -1");
  VSET(79, e16, m4);
  asm volatile("vcpop.m %[A], v2 \n"
               "sw %[A], (%1) \n"
               :
               : [A] "r"(scalar), "r"(OUP));
  XCMP(9, OUP[0], 79);
}

// Back-to-back scalar mask operations must not share accumulator state.
void TEST_CASE3(void) {
  VSET(1, e8, m1);
  VLOAD_8(v11, 0x01);
  VLOAD_8(v24, 0x08);
  VLOAD_8(v0, 0x08);
  VLOAD_8(v19, 0x00);

  uint64_t first;
  uint64_t count;
  uint64_t scratch;
  const uint64_t compare = 0;
  asm volatile(
      "vsetivli zero, 7, e8, mf8, tu, mu\n"
      "vfirst.m %[first], v11\n"
      "vmsleu.vx v5, v19, %[compare], v0.t\n"
      "remu %[scratch], %[first], %[divisor]\n"
      "vcpop.m %[count], v24, v0.t\n"
      : [first] "=&r"(first), [count] "=&r"(count),
        [scratch] "=&r"(scratch)
      : [compare] "r"(compare), [divisor] "r"(UINT64_C(3))
      : "memory");

  XCMP(10, first, 0);
  XCMP(11, count, 1);
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  enable_fp();
  TEST_CASE1();
  TEST_CASE2();
  TEST_CASE3();
  EXIT_CHECK();
}
