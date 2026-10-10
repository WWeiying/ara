// SPDX-License-Identifier: Apache-2.0
// Use an FP seed requester, which carries source_version, to test whether
// an LMUL group overwrite invalidates a cached scalar in an interior register.
// Values are FP32 subnormal bit patterns: exact result bits are 32 + 7 = 39.
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
    "li t0, 64\n"
    "vsetvli t0, t0, e32, m2, tu, mu\n"
    "vmv.v.i v8, 7\n"
    "csrr zero, vstart\n"
    "li t0, 32\n"
    "vsetvli t0, t0, e32, m1, tu, mu\n"
    "vfredusum.vs v10, v1, v9\n"
    "vmv.x.s %[result], v10\n"
    : [result] "=&r"(result) : : "t0", "memory");
  int fail = result != 39;
  printf("FP group overwrite audit: got=%lu expected=39 %s\n", result, fail ? "FAIL" : "PASS");
  return fail;
}
