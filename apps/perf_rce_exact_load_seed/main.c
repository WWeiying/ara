// SPDX-License-Identifier: Apache-2.0
// FP32 exact-path baseline probe for the seed RAW of a vector Load producer.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint32_t seeds[64] __attribute__((aligned(128)));
static int probe(uint64_t vl) {
  uint64_t start, end, a, b;
  asm volatile(
    "vsetvli t0, %[vl], e32, m1, tu, mu\n"
    "li t0, 0x3f800000\nvmv.v.x v8, t0\n"
    "csrr zero, vstart\ncsrr %[start], cycle\n"
    ".rept 8\n"
    "vle32.v v4, (%[data])\nvfredusum.vs v24, v8, v4\n"
    "vle32.v v4, (%[data])\nvfredusum.vs v25, v8, v4\n"
    ".endr\n"
    "csrr zero, vstart\ncsrr %[end], cycle\n"
    "vmv.x.s %[a], v24\nvmv.x.s %[b], v25\n"
    : [start] "=&r"(start), [end] "=&r"(end), [a] "=&r"(a), [b] "=&r"(b)
    : [vl] "r"(vl), [data] "r"(seeds) : "t0", "memory");
  union { float f; uint32_t u; } expected = {.f = (float)(vl+3)};
  if ((uint32_t)a != expected.u || (uint32_t)b != expected.u) {
    printf("FAIL Load seed vl=%lu a=%lx b=%lx expected=%lx\n",vl,a,b,(uint64_t)expected.u);
    return 1;
  }
  printf("RCE Load seed PASS: pairs=16 vl=%lu sew=32 lmul=1 cycles=%lu\n",vl,end-start);
  return 0;
}
int main(void) {
  for (unsigned i=0;i<64;i++) seeds[i]=0x40400000U;
  asm volatile("fence rw,rw\nvsetvli t0,zero,e8,m8,tu,mu\nvmv.v.i v0,0\nvmv.v.i v8,0\nvmv.v.i v16,0\nvmv.v.i v24,0\n" ::: "t0", "memory");
  return probe(1) || probe(4) || probe(16) || probe(32);
}
