// SPDX-License-Identifier: Apache-2.0
// A Slide owns the physical egress between two FP64 frames. Short vectors
// give empty lanes an opportunity to reach the next header early.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint64_t slide_out[16] __attribute__((aligned(128)));
static int run(unsigned vl, uint64_t expected) {
  uint64_t a,b,c;
  asm volatile(
    "vsetvli t0, zero, e64, m1, tu, mu\n"
    "li t0, 0x3ff0000000000000\nvmv.v.x v4, t0\n"
    "li t0, 0x4008000000000000\nvmv.v.x v2, t0\nvmv.v.i v6, 7\n"
    "vsetvli t0, %[vl], e64, m1, tu, mu\n"
    "vfredusum.vs v8, v4, v2\n"
    "vslidedown.vi v10, v6, 1\n"
    "vfredusum.vs v12, v4, v2\n"
    "vfadd.vv v14, v4, v4\n"
    "vmv.x.s %[a], v8\nvmv.x.s %[b], v12\nvmv.x.s %[c], v14\n"
    "vse64.v v10, (%[out])\ncsrr zero, vstart\n"
    : [a] "=&r"(a),[b] "=&r"(b),[c] "=&r"(c)
    : [vl] "r"((uint64_t)vl),[out] "r"(slide_out) : "t0","memory");
  if(a!=expected || b!=expected || c!=0x4000000000000000ULL) {
    printf("FAIL FP64 Slide vl=%u a=%lx b=%lx add=%lx\n",vl,a,b,c);return 1;
  }
  for(unsigned i=0;i<vl;i++) if(slide_out[i]!=(i==15?0:7)) {
    printf("FAIL FP64 Slide element vl=%u i=%u value=%lx\n",vl,i,slide_out[i]);return 1;
  }
  return 0;
}
int main(void) {
  if(run(1,0x4010000000000000ULL) || run(4,0x401c000000000000ULL) || run(16,0x4033000000000000ULL)) return 1;
  printf("RCE FP64 Slide PASS: VL=1/4/16, shared egress ownership\n");return 0;
}
