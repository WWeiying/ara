// SPDX-License-Identifier: Apache-2.0
// Check the mask population before attributing a mismatch to reduction.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static const uint16_t src[16] __attribute__((aligned(32))) = {
  0x3c00,0x4000,0x4200,0x4400,0x4500,0x4600,0x4700,0x4800,
  0x3c00,0x4000,0x4200,0x4400,0x4500,0x4600,0x4700,0x4800
};
static const uint8_t mask[128] __attribute__((aligned(32))) = {0xaa, 0x55};
int main(void) {
  uint64_t ordered, unordered, count;
  asm volatile(
    "li t0, 1\n"
    "vsetvli t0, t0, e32, m1, tu, mu\n"
    "li t0, 0x3f800000\n"
    "vmv.v.x v2, t0\n"
    "csrr zero, vstart\n"
    "li t0, 2\n"
    "vsetvli t0, t0, e8, m1, tu, mu\n"
    "vle8.v v0, (%[mask])\n"
    "csrr zero, vstart\n"
    "li t0, 16\n"
    "vsetvli t0, t0, e16, m1, tu, mu\n"
    "vle16.v v6, (%[src])\n"
    "csrr zero, vstart\n"
    "vcpop.m %[count], v0\n"
    "vfwredosum.vs v8, v6, v2, v0.t\n"
    "vfwredusum.vs v10, v6, v2, v0.t\n"
    "li t0, 1\n"
    "vsetvli t0, t0, e32, m1, tu, mu\n"
    "vmv.x.s %[ordered], v8\n"
    "vmv.x.s %[unordered], v10\n"
    : [ordered] "=&r"(ordered), [unordered] "=&r"(unordered), [count] "=&r"(count)
    : [src] "r"(src), [mask] "r"(mask) : "t0", "memory");
  int fail = ordered != 0x42140000 || unordered != 0x42140000 || count != 8;
  printf("widen mask audit: ordered=%lx unordered=%lx count=%lu %s\n",
         ordered, unordered, count, fail ? "FAIL" : "PASS");
  return fail;
}
