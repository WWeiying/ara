// SPDX-License-Identifier: Apache-2.0
// A group writer must replace cached scalar seeds in every destination member.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
#define CASE(REG, SETUP, WRITE) do { \
  uint64_t result; \
  asm volatile( \
    "li t0, 32\n vsetvli zero, t0, e32, m1, tu, mu\n" \
    "vmv.v.i v1, 1\n vmv.v.i v2, 0\n" \
    "vfredusum.vs " REG ", v1, v2\n csrr zero, vstart\n" \
    SETUP WRITE "csrr zero, vstart\n" \
    "li t0, 32\n vsetvli zero, t0, e32, m1, tu, mu\n" \
    "vfredusum.vs v20, v1, " REG "\n vmv.x.s %[result], v20\n" \
    : [result] "=&r"(result) :: "t0", "t1", "memory"); \
  ++cases; \
  if (result != 39) { \
    printf("group matrix case=%u got=%lu expected=39 FAIL\n", cases, result); \
    return 1; \
  } \
} while (0)
int main(void) {
  unsigned cases=0;
  CASE("v9", "li t0, 64\n vsetvli zero, t0, e32, m2, tu, mu\n", "vmv.v.i v8, 7\n");
  CASE("v11", "li t0, 128\n vsetvli zero, t0, e32, m4, tu, mu\n", "vmv.v.i v8, 7\n");
  CASE("v15", "li t0, 256\n vsetvli zero, t0, e32, m8, tu, mu\n", "vmv.v.i v8, 7\n");
  CASE("v9", "li t0, 16\n vsetvli zero, t0, e32, mf2, tu, mu\n", "vmv.v.i v9, 7\n");
  // e16,m1 widening writes an e32,m2 destination group, including v9.
  CASE("v9", "li t0, 64\n vsetvli zero, t0, e16, m1, tu, mu\n",
       "vmv.v.i v16, 3\n li t1, 4\n vwadd.vx v8, v16, t1\n");
  printf("group matrix: %u cases PASS\n",cases);
  return 0;
}
