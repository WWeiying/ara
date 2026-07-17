// SPDX-License-Identifier: Apache-2.0
// Protocol-level performance probe for unequal per-lane exact-state windows.

#include <stdint.h>

#include "printf.h"
#include "runtime.h"

static const uint32_t __attribute__((aligned(32))) input[4] = {
    0x60ad78ec,  // +1e20: wide positive exact state
    0x3f800000,  // +1: short positive state
    0xe0ad78ec,  // -1e20: wide negative exact state
    0x00000000,  // zero: short state
};

int main(void) {
  uint64_t mismatch;

  asm volatile(
      "li t0, 4\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      "vle32.v v1, (%[src])\n"
      "vmv.v.i v2, 0\n"
      "vmv.x.s t1, v2\n"
      "fence\n"
      "rdcycle zero\n"
      "vfredusum.vs v4, v1, v2\n"
      "vfredusum.vs v5, v1, v2\n"
      "vfredusum.vs v6, v1, v2\n"
      "vfredusum.vs v7, v1, v2\n"
      "vmv.x.s t2, v7\n"
      "fence\n"
      "rdcycle zero\n"
      "li t3, 0\n"
      "li t4, 0x3f800000\n"
      "vmv.x.s t2, v4\n"
      "xor t2, t2, t4\n"
      "or t3, t3, t2\n"
      "vmv.x.s t2, v5\n"
      "xor t2, t2, t4\n"
      "or t3, t3, t2\n"
      "vmv.x.s t2, v6\n"
      "xor t2, t2, t4\n"
      "or t3, t3, t2\n"
      "vmv.x.s t2, v7\n"
      "xor t2, t2, t4\n"
      "or t3, t3, t2\n"
      "mv %[mismatch], t3\n"
      : [mismatch] "=&r"(mismatch)
      : [src] "r"(input)
      : "t0", "t1", "t2", "t3", "t4", "memory");

  printf("sparse exact-window probe: mismatch=%lx (%s)\n", mismatch,
         mismatch ? "FAILED" : "PASSED");
  return mismatch != 0;
}
