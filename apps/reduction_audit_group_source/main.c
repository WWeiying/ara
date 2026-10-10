// SPDX-License-Identifier: Apache-2.0
// A vector source spanning v8/v9 must not match an old cached scalar v9
// using the epoch of group base v8. All subnormal additions are exact.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
int main(void) {
  uint64_t result;
  asm volatile(
    "li t0, 32\n"
    "vsetvli t0, t0, e32, m1, tu, mu\n"
    "vmv.v.i v1, 1\n"
    "vmv.v.i v2, 0\n"
    "vfredusum.vs v9, v1, v2\n"
    "csrr zero, vstart\n"
    "li t0, 33\n"
    "vsetvli t0, t0, e32, m2, tu, mu\n"
    "vmv.v.i v8, 7\n"
    "csrr zero, vstart\n"
    "vfredusum.vs v10, v8, v2\n"
    "vmv.x.s %[result], v10\n"
    : [result] "=&r"(result) : : "t0", "memory");
  int fail = result != 231;
  printf("FP group source audit: got=%lu expected=231 %s\n", result, fail ? "FAIL" : "PASS");
  return fail;
}
