// SPDX-License-Identifier: Apache-2.0
// A write to an LMUL group must invalidate cached scalars in every member.
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
    "vredsum.vs v9, v1, v2\n"
    "csrr zero, vstart\n"
    "li t0, 64\n"
    "vsetvli t0, t0, e32, m2, tu, mu\n"
    "vmv.v.i v8, 7\n"
    "csrr zero, vstart\n"
    "li t0, 32\n"
    "vsetvli t0, t0, e32, m1, tu, mu\n"
    "vredsum.vs v10, v1, v9\n"
    "vmv.x.s %[result], v10\n"
    : [result] "=&r"(result) : : "t0", "memory");
  int fail = result != 39;
  printf("group overwrite audit: got=%lu expected=39 %s\n", result, fail ? "FAIL" : "PASS");
  return fail;
}
