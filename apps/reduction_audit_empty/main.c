// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
int main(void) {
  uint64_t result, flags;
  asm volatile(
    "li t0, 7\n"
    "vsetvli t0, t0, e32, m1, tu, mu\n"
    "li t0, 0x7fa12345\n" // sNaN seed must be copied or legally canonicalized.
    "vmv.v.x v2, t0\n"
    "vmv.v.i v1, 1\n"
    "vmv.v.i v0, 0\n"
    "vmclr.m v0\n"
    "vmv.v.i v4, 0\n"
    "csrwi fflags, 0\n"
    "rdcycle zero\n"
    "vfredusum.vs v4, v1, v2, v0.t\n"
    "vmv.x.s %[result], v4\n"
    "csrr %[flags], fflags\n"
    "rdcycle zero\n"
    : [result] "=&r"(result), [flags] "=&r"(flags) : : "t0", "memory");
  int fail = !((result == 0x7fa12345 && flags == 0) ||
               (result == 0x7fc00000 && flags == 16));
  printf("empty sum audit: result=%lx flags=%lx %s\n", result, flags, fail ? "FAIL" : "PASS");
  return fail;
}
