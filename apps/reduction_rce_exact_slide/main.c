// SPDX-License-Identifier: Apache-2.0
// A Slide owns the physical egress between two exact frames. Short vectors
// give empty lanes an opportunity to reach the next header early.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint32_t slide_out[32] __attribute__((aligned(128)));
static int run(unsigned vl, uint64_t expected) {
  uint64_t a,b,c;
  asm volatile(
    "vsetvli t0, zero, e32, m1, tu, mu\n"
    "li t0, 0x3f800000\nvmv.v.x v4, t0\n"
    "li t0, 0x40400000\nvmv.v.x v2, t0\nvmv.v.i v6, 7\n"
    "vsetvli t0, %[vl], e32, m1, tu, mu\n"
    "vfredusum.vs v8, v4, v2\n"
    "vslidedown.vi v10, v6, 1\n"
    "vfredusum.vs v12, v4, v2\n"
    "vfadd.vv v14, v4, v4\n"
    "vmv.x.s %[a], v8\nvmv.x.s %[b], v12\nvmv.x.s %[c], v14\n"
    "vse32.v v10, (%[out])\ncsrr zero, vstart\n"
    : [a] "=&r"(a),[b] "=&r"(b),[c] "=&r"(c)
    : [vl] "r"((uint64_t)vl),[out] "r"(slide_out) : "t0","memory");
  if(a!=expected || b!=expected || c!=0x40000000) {
    printf("FAIL exact Slide vl=%u a=%lx b=%lx add=%lx\n",vl,a,b,c);return 1;
  }
  for(unsigned i=0;i<vl;i++) if(slide_out[i]!=(i==31?0:7)) {
    printf("FAIL exact Slide element vl=%u i=%u value=%x\n",vl,i,slide_out[i]);return 1;
  }
  return 0;
}
int main(void) {
  if(run(1,0x40800000) || run(4,0x40e00000) || run(32,0x420c0000)) return 1;
  printf("RCE exact Slide PASS: VL=1/4/32, shared egress ownership\n");return 0;
}
