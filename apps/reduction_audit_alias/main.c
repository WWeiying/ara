// SPDX-License-Identifier: Apache-2.0
// Adjacent ordered reductions are duplicates only if the first write leaves
// every source of the second instruction unchanged. Subnormal inputs make
// all sums exact and permit checking the result directly as integer bits.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"

int main(void) {
  uint64_t seed_chain, source_overlap;
  asm volatile(
      "li t0, 32\n"
      "vsetvli t0, t0, e32, m1, tu, mu\n"
      "vmv.v.i v1, 1\n"
      "vmv.v.i v2, 0\n"
      "vfredosum.vs v2, v1, v2\n"
      "vfredosum.vs v2, v1, v2\n"
      "vmv.x.s %[result], v2\n"
      : [result] "=&r"(seed_chain) : : "t0", "memory");
  asm volatile(
      "li t0, 32\n"
      "vsetvli t0, t0, e32, m1, tu, mu\n"
      "vmv.v.i v1, 1\n"
      "vmv.v.i v2, 0\n"
      "vfredosum.vs v1, v1, v2\n"
      "vfredosum.vs v3, v1, v2\n"
      "vmv.x.s %[result], v3\n"
      : [result] "=&r"(source_overlap) : : "t0", "memory");
  int failed = seed_chain != 64 || source_overlap != 63;
  printf("ordered alias audit: seed=%lu/64 source=%lu/63 %s\n",
         seed_chain, source_overlap, failed ? "FAIL" : "PASS");
  return failed;
}
