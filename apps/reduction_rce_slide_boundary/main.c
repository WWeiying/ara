// SPDX-License-Identifier: Apache-2.0
// Isolate the inherited Slide boundary failure found by the RCE shared-port test.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint8_t output[VLEN/4] __attribute__((aligned(128)));
#define S_(x) #x
#define S(x) S_(x)
#define CASE(W,NAME,L,M,D) \
static int NAME(unsigned trim,unsigned offset) { \
  unsigned maximum=(VLEN/W)*M/D, vl=maximum-trim; \
  asm volatile( \
    "vsetvli t0, zero, e" S(W) ", m2, tu, mu\n" \
    "vmv.v.i v8, -2\nvmv.v.i v10, -2\nvmv.v.i v16, -1\n" \
    "vsetvli t0, zero, e" S(W) ", " S(L) ", tu, mu\n" \
    "vmv.v.i v8, 5\n" \
    "vsetvli t0, %[vl], e" S(W) ", " S(L) ", tu, mu\n" \
    "vslidedown.vx v16, v8, %[offset]\n" \
    "vse" S(W) ".v v16, (%[out])\ncsrr zero, vstart\n" \
    : : [vl] "r"((uint64_t)vl), [offset] "r"((uint64_t)offset), [out] "r"(output) \
    : "t0","memory"); \
  for(unsigned i=0;i<vl;i++) { \
    uint64_t actual=0; \
    for(unsigned b=0;b<W/8;b++) actual|=(uint64_t)output[i*(W/8)+b]<<(8*b); \
    uint64_t expected=i+offset<maximum?5:0; \
    if(actual!=expected) { \
      printf("FAIL Slide boundary sew=%u lmul=" S(L) " vl=%u offset=%u i=%u actual=%lx expected=%lx\n", W,vl,offset,i,actual,expected); \
      return 1; \
    } \
  } \
  return 0; \
}
#define WIDTH(W) CASE(W,run##W##m1,m1,1,1) CASE(W,run##W##m2,m2,2,1) CASE(W,run##W##mf2,mf2,1,2)
WIDTH(8)
WIDTH(16)
WIDTH(32)
// ELEN=64 requires SEW <= LMUL*ELEN for fractional LMUL. e64/mf2
// sets vill in this Ara configuration and is not a positive Slide case.
CASE(64,run64m1,m1,1,1)
CASE(64,run64m2,m2,2,1)
int main(void) {
  int (*runs[])(unsigned,unsigned)={run8m1,run8m2,run8mf2,run16m1,run16m2,run16mf2,
    run32m1,run32m2,run32mf2,run64m1,run64m2};
  for(unsigned r=0;r<sizeof(runs)/sizeof(runs[0]);r++)
    for(unsigned trim=0;trim<2;trim++)
      for(unsigned offset=1;offset<=3;offset+=2)
        if(runs[r](trim,offset)) return 1;
  printf("Slide boundary PASS: 44 legal cases, 4 SEWs, m1/m2/mf2, VL and VLMAX distinct\n");
  return 0;
}
