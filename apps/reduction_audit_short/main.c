// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
int main(void) {
  uint64_t result, flags;
  asm volatile(
    "li t0, 1\n"
    "vsetvli t0, t0, e32, m1, tu, mu\n"
    "li t0, 0x3f800000\n" // 1.0 seed.
    "vmv.v.x v2, t0\n"
    "vmv.v.x v1, t0\n"
    "vmv.v.i v0, 0\n"
    "vmset.m v0\n"
    "vmv.v.i v4, 0\n"
    "csrwi fflags, 0\n"
    "rdcycle zero\n"
    "vfredusum.vs v4, v1, v2, v0.t\n"
    "vmv.x.s %[result], v4\n"
    "csrr %[flags], fflags\n"
    "rdcycle zero\n"
    : [result] "=&r"(result), [flags] "=&r"(flags) : : "t0", "memory");
  int fail = result != 0x40000000 || flags != 0;
  printf("VL=1 sum audit: result=%lx flags=%lx %s\n", result, flags, fail ? "FAIL" : "PASS");
  return fail;
}
