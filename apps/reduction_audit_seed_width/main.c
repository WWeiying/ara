// SPDX-License-Identifier: Apache-2.0
// A narrow producer does not define the upper bytes of a wider scalar seed.
// Exercise adjacent native and widening reductions under one architectural
// SEW=16 setting; normal reshuffle/hazard handling must preserve those bytes.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"

int main(void) {
  uint64_t wide, narrow;
  asm volatile(
      "li t0, 16\n"
      "vsetvli t0, t0, e32, m1, tu, mu\n"
      "li t1, 0x3f800000\n"
      "vmv.v.x v16, t1\n"
      "li t0, 16\n"
      "vsetvli t0, t0, e16, m1, tu, mu\n"
      "vmv.v.i v8, 0\n"
      "vmv.v.i v24, 0\n"
      "vfredusum.vs v16, v8, v24\n"
      "vfwredusum.vs v20, v8, v16\n"
      "vsetivli zero, 1, e32, m1, tu, mu\n"
      "vmv.x.s %[wide], v20\n"
      "li t0, 16\n"
      "vsetvli t0, t0, e32, m1, tu, mu\n"
      "li t1, 0x3f803c00\n"
      "vmv.v.x v24, t1\n"
      "li t0, 16\n"
      "vsetvli t0, t0, e16, m1, tu, mu\n"
      "vfwredusum.vs v16, v8, v24\n"
      "vfredusum.vs v20, v8, v16\n"
      "vmv.x.s %[narrow], v20\n"
      : [wide] "=&r"(wide), [narrow] "=&r"(narrow)
      : : "t0", "t1", "memory");
  int failed = wide != 0x3f800000 || narrow != 0x3c00;
  printf("seed width audit: wide=%lx/3f800000 narrow=%lx/3c00 %s\n",
         wide, narrow, failed ? "FAIL" : "PASS");
  return failed;
}
