// Copyright 2021 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Author: Matteo Perotti <mperotti@iis.ee.ethz.ch>

#include "vector_macros.h"

// Load only the supplied seed/mask elements; VLOAD follows the current VL.
// Reading a one-element stack array with VL=16 reads outside that array.

// Naive test
void TEST_CASE1(void) {
  VSET(16, e8, m1);
  // VCMP stores a full vector; define tail bytes before the first reduction.
  VCLEAR(v3);
  VLOAD_8(v1, 1, 2, 3, 4, 5, 6, 7, 0, 1, 9, 3, 4, 5, 6, 7, 8);
  VSET(1, e8, m1);
  VLOAD_8(v2, 1);
  VSET(16, e8, m1);
  asm volatile("vredmin.vs v3, v1, v2");
  VCMP_U8(1, v3, 0);

  VSET(16, e16, m1);
  VLOAD_16(v1, 1, 2, -3, 4, 5, 6, 7, 8, 1, 2, 3, 4, 5, 6, 7, 8);
  VSET(1, e16, m1);
  VLOAD_16(v2, 0);
  VSET(16, e16, m1);
  asm volatile("vredmin.vs v3, v1, v2");
  VCMP_U16(2, v3, -3);

  VSET(16, e32, m1);
  VLOAD_32(v1, 9, 2, 3, 4, 5, 6, 7, 8, 1, 2, 3, 4, 5, 6, 7, 8);
  VSET(1, e32, m1);
  VLOAD_32(v2, -1);
  VSET(16, e32, m1);
  asm volatile("vredmin.vs v3, v1, v2");
  VCMP_U32(3, v3, -1);

  VSET(16, e64, m1);
  VLOAD_64(v1, -1, 2, 3, 4, 5, -6, 7, -9, -1, -2, 3, 4, 5, 6, 7, 8);
  VSET(1, e64, m1);
  VLOAD_64(v2, -1);
  VSET(16, e64, m1);
  asm volatile("vredmin.vs v3, v1, v2");
  VCMP_U64(4, v3, -9);
}
// Masked naive test
void TEST_CASE2(void) {
  VSET(16, e8, m1);
  VSET(2, e8, m1);
  VLOAD_8(v0, 0x03, 0x00);
  VSET(16, e8, m1);
  VLOAD_8(v1, 1, -2, 3, 4, 5, 6, 7, 9, 1, 2, 3, 4, 5, 6, 7, 8);
  VSET(1, e8, m1);
  VLOAD_8(v2, 1);
  VSET(16, e8, m1);
  VSET(1, e8, m1);
  VLOAD_8(v3, 1);
  VSET(16, e8, m1);
  asm volatile("vredmin.vs v3, v1, v2, v0.t");
  VCMP_U8(5, v3, -2);

  VSET(16, e16, m1);
  VSET(2, e8, m1);
  VLOAD_8(v0, 0x00, 0xc0);
  VSET(16, e16, m1);
  VLOAD_16(v1, -1, 2, 3, 4, 5, 6, 7, 8, 1, 2, 3, 4, 5, 6, 7, 8);
  VSET(1, e16, m1);
  VLOAD_16(v2, 3);
  VSET(16, e16, m1);
  VSET(1, e16, m1);
  VLOAD_16(v3, 1);
  VSET(16, e16, m1);
  asm volatile("vredmin.vs v3, v1, v2, v0.t");
  VCMP_U16(6, v3, 3);

  VSET(16, e32, m1);
  VSET(2, e8, m1);
  VLOAD_8(v0, 0x00, 0xc0);
  VSET(16, e32, m1);
  VLOAD_32(v1, 1, 2, 3, 4, 5, 6, 7, 8, 1, 2, 3, 4, 5, 6, 7, 8);
  VSET(1, e32, m1);
  VLOAD_32(v2, 8);
  VSET(16, e32, m1);
  VSET(1, e32, m1);
  VLOAD_32(v3, 1);
  VSET(16, e32, m1);
  asm volatile("vredmin.vs v3, v1, v2, v0.t");
  VCMP_U32(7, v3, 7);

  VSET(16, e64, m1);
  VSET(2, e8, m1);
  VLOAD_8(v0, 0xaa, 0x55);
  VSET(16, e64, m1);
  VLOAD_64(v1, 1, 2, 3, 4, 5, 6, 7, 8, 1, 2, 3, 4, 5, 6, 7, 8);
  VSET(1, e64, m1);
  VLOAD_64(v2, 4);
  VSET(16, e64, m1);
  VSET(1, e64, m1);
  VLOAD_64(v3, 1);
  VSET(16, e64, m1);
  asm volatile("vredmin.vs v3, v1, v2, v0.t");
  VCMP_U64(8, v3, 1);
}

int main(void) {
  INIT_CHECK();
  enable_vec();

  TEST_CASE1();
  TEST_CASE2();

  EXIT_CHECK();
}
