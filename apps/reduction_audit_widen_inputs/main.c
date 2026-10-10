// SPDX-License-Identifier: Apache-2.0
// Diagnose operands after an FP32->FP64 to FP16->FP32 masked transition.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint16_t observed[16] __attribute__((aligned(32)));
static uint8_t observed_mask[32] __attribute__((aligned(32)));
int main(void) {
  volatile uint64_t seed64[] = {0x3ff0000000000000};
  volatile uint32_t src32[] = {
    0x3f800000,0x40000000,0x40400000,0x40800000,0x40a00000,0x40c00000,0x40e00000,0x41000000,
    0x3f800000,0x40000000,0x40400000,0x40800000,0x40a00000,0x40c00000,0x40e00000,0x41000000};
  volatile uint32_t seed32[] = {0x3f800000};
  volatile uint8_t mask[] = {0xaa,0x55};
  volatile uint16_t src16[] = {0x3c00,0x4000,0x4200,0x4400,0x4500,0x4600,0x4700,0x4800,
                              0x3c00,0x4000,0x4200,0x4400,0x4500,0x4600,0x4700,0x4800};
  uint64_t first, result, count;
  asm volatile(
    "li t0, 1\n vsetvli zero, t0, e64, m1, tu, mu\n"
    "csrr zero, vstart\n vle64.v v2, (%[s64])\n"
    "li t0, 16\n vsetvli zero, t0, e32, m1, tu, mu\n"
    "csrr zero, vstart\n vle32.v v6, (%[x32])\n"
    "vfwredosum.vs v4, v6, v2\n"
    "li t0, 1\n vsetvli zero, t0, e64, m1, tu, mu\n vmv.x.s %[first], v4\n"
    "vsetvli zero, t0, e32, m1, tu, mu\n"
    "csrr zero, vstart\n vle32.v v2, (%[s32])\n"
    "li t0, 2\n vsetvli zero, t0, e8, m1, tu, mu\n"
    "csrr zero, vstart\n vle8.v v0, (%[mask])\n"
    "li t0, 16\n vsetvli zero, t0, e16, m1, tu, mu\n"
    "csrr zero, vstart\n vle16.v v6, (%[x16])\n"
    "vfwredosum.vs v4, v6, v2, v0.t\n"
    "csrr zero, vstart\n vse16.v v6, (%[observed])\n"
    "vsm.v v0, (%[observed_mask])\n vcpop.m %[count], v0\n"
    "li t0, 1\n vsetvli zero, t0, e32, m1, tu, mu\n vmv.x.s %[result], v4\n"
    "csrr zero, vstart\n"
    : [first] "=&r"(first), [result] "=&r"(result), [count] "=&r"(count)
    : [s64] "r"(seed64), [x32] "r"(src32), [s32] "r"(seed32), [mask] "r"(mask),
      [x16] "r"(src16), [observed] "r"(observed), [observed_mask] "r"(observed_mask)
    : "t0", "memory");
  int failed = first != 0x4052400000000000 || result != 0x42140000 || count != 8;
  printf("widen inputs: first=%lx result=%lx count=%lu mask=%x/%x\n",
         first,result,count,observed_mask[0],observed_mask[1]);
  for (unsigned i=0;i<16;++i) {
    if (observed[i] != src16[i])
      printf("source[%u]=%x expected=%x\n",i,observed[i],src16[i]);
    failed |= observed[i] != src16[i];
  }
  failed |= observed_mask[0] != 0xaa || observed_mask[1] != 0x55;
  printf("widen input audit %s\n",failed ? "FAIL" : "PASS");
  return failed;
}
