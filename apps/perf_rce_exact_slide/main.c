// SPDX-License-Identifier: Apache-2.0
// Same ELF for original tail, dedicated tail, and dedicated tail + mixed issue.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
#define PAIR(R,A) "vfredusum.vs " R ", v4, v2\nvslidedown.vi " A ", v14, 1\n"
static uint32_t slides[4][32] __attribute__((aligned(128)));
int main(void) {
  uint64_t start,end,a,b,c,d,add;
  asm volatile(
    "li t0, 32\nvsetvli t0, t0, e32, m1, tu, mu\n"
    "li t0, 0x3f800000\nvmv.v.x v4, t0\nli t0, 0x40400000\nvmv.v.x v2, t0\n"
    "li t0, 0x40800000\nvmv.v.x v14, t0\nli t0, 0x40a00000\nvmv.v.x v16, t0\n"
    "csrr zero, vstart\ncsrr %[start], cycle\n"
    ".rept 8\n"
    PAIR("v8","v12") PAIR("v10","v18")
    PAIR("v20","v24") PAIR("v22","v26")
    ".endr\n"
    "csrr zero, vstart\ncsrr %[end], cycle\n"
    "vmv.x.s %[a], v8\nvmv.x.s %[b], v10\n"
    "vmv.x.s %[c], v20\nvmv.x.s %[d], v22\nvmv.x.s %[add], v26\n"
    : [start] "=&r"(start), [end] "=&r"(end), [a] "=&r"(a),
      [b] "=&r"(b), [c] "=&r"(c), [d] "=&r"(d), [add] "=&r"(add)
    : : "t0", "memory");
  if(a!=0x420c0000 || b!=0x420c0000 || c!=0x420c0000 || d!=0x420c0000 || add!=0x40800000) {
    printf("FAIL RCE exact Slide probe a=%lu b=%lu c=%lu d=%lu add=%lu\n",a,b,c,d,add);
    return 1;
  }
  asm volatile("vse32.v v12,(%0)\nvse32.v v18,(%1)\nvse32.v v24,(%2)\nvse32.v v26,(%3)\ncsrr zero,vstart\n"
    :: "r"(slides[0]),"r"(slides[1]),"r"(slides[2]),"r"(slides[3]) : "memory");
  for(unsigned j=0;j<4;j++)for(unsigned i=0;i<32;i++)if(slides[j][i]!=(i==31?0:0x40800000U)) {
    printf("FAIL RCE exact Slide vector j=%u i=%u got=%x\n",j,i,slides[j][i]);return 1;
  }
  printf("RCE exact Slide probe PASS: pairs=32 vl=32 sew=32 cycles=%lu\n",end-start);
  return 0;
}
