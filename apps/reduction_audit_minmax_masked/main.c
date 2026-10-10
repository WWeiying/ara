// SPDX-License-Identifier: Apache-2.0
// +/-infinity is not an identity for minimumNumber/maximumNumber when the
// other argument is NaN. Empty subtrees must not turn an all-NaN reduction
// into a numeric infinity, and an all-masked operation must copy the seed.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"

int main(void) {
  uint64_t min_result, max_result, masked_result, flags;
  asm volatile(
      "li t0, 32\n"
      "vsetvli t0, t0, e32, m1, tu, mu\n"
      "li t0, 0x7fc12345\n"
      "vmv.v.x v1, t0\n"
      "vmv.v.x v2, t0\n"
      "vmv.v.i v0, 0\n"
    "vmclr.m v0\n"
      "vmv.v.i v4, 0\n"
      "vmv.v.i v6, 0\n"
      "vmv.v.i v8, 0\n"
      "csrwi fflags, 0\n"
      "vfredmin.vs v4, v1, v2\n"
      "vfredmax.vs v6, v1, v2\n"
      "vfredmin.vs v8, v1, v2, v0.t\n"
      "vmv.x.s %[min_result], v4\n"
      "vmv.x.s %[max_result], v6\n"
      "vmv.x.s %[masked_result], v8\n"
      "csrr %[flags], fflags\n"
      : [min_result] "=&r"(min_result), [max_result] "=&r"(max_result),
        [masked_result] "=&r"(masked_result), [flags] "=&r"(flags)
      : : "t0", "memory");
  int failed = min_result != 0x7fc00000 || max_result != 0x7fc00000 ||
               masked_result != 0x7fc12345 || flags != 0;
  printf("minmax NaN audit: min=%lx max=%lx masked=%lx flags=%lx %s\n",
         min_result, max_result, masked_result, flags, failed ? "FAIL" : "PASS");
  return failed;
}
