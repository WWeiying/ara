// SPDX-License-Identifier: Apache-2.0
// Identical source values and vtype/vl must use the same unordered tree even
// when the scalar seed is produced by an immediately preceding reduction.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"

static const uint32_t __attribute__((aligned(32))) body[8] = {
    0x7f800000, 0, 0, 0, 0xff800000, 0, 0, 0};
static const uint32_t __attribute__((aligned(32))) producer[8] = {
    0x7fc00000, 0, 0, 0, 0, 0, 0, 0};

int main(void) {
  uint64_t plain_result, plain_flags, chain_result, chain_flags;
  asm volatile(
      "li t0, 8\n"
      "vsetvli t0, t0, e32, m1, tu, mu\n"
      "vle32.v v1, (%[producer])\n"
      "vle32.v v3, (%[body])\n"
      "vmv.v.i v2, 0\n"
      "li t0, 0x7fc00000\n"
      "vmv.v.x v4, t0\n"
      "vmv.x.s t0, v4\n"
      "csrwi fflags, 0\n"
      "vfredusum.vs v5, v3, v4\n"
      "vmv.x.s %[plain_result], v5\n"
      "csrr %[plain_flags], fflags\n"
      "csrwi fflags, 0\n"
      "vfredusum.vs v4, v1, v2\n"
      "vfredusum.vs v6, v3, v4\n"
      "vmv.x.s %[chain_result], v6\n"
      "csrr %[chain_flags], fflags\n"
      : [plain_result] "=&r"(plain_result), [plain_flags] "=&r"(plain_flags),
        [chain_result] "=&r"(chain_result), [chain_flags] "=&r"(chain_flags)
      : [producer] "r"(producer), [body] "r"(body)
      : "t0", "memory");
  int failed = plain_result != 0x7fc00000 || chain_result != 0x7fc00000 ||
               plain_flags != 16 || chain_flags != 16;
  printf("seed tree audit: plain=%lx/%lx chain=%lx/%lx %s\n",
         plain_flags, plain_result, chain_flags, chain_result,
         failed ? "FAIL" : "PASS");
  return failed;
}
