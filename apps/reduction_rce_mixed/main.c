// SPDX-License-Identifier: Apache-2.0
// Independent ordinary ALU work during reduction completion, followed by a
// true seed RAW and a true vector RAW. Check full vector output including TU.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint64_t output[VLEN/64] __attribute__((aligned(128)));
#define STR_(x) #x
#define STR(x) STR_(x)
#define RUN(W) \
static int run##W(unsigned vl) { \
  uint64_t a,b,c; \
  asm volatile( \
    "li t0, " STR(VLEN/W) "\n" \
    "vsetvli t0, t0, e" STR(W) ", m1, tu, mu\n" \
    "vmv.v.i v4, 1\nvmv.v.i v6, 2\nvmv.v.i v2, 3\n" \
    "vmv.v.i v14, 4\nvmv.v.i v16, 5\nvmv.v.i v12, -1\nvmv.v.i v10, -1\n" \
    "vsetvli t0, %[vl], e" STR(W) ", m1, tu, mu\n" \
    "vredsum.vs v8, v4, v2\n" \
    "vadd.vv v12, v14, v16\n" \
    "vredsum.vs v10, v6, v8\n" \
    "vadd.vv v18, v10, v16\n" \
    "vmv.x.s %[a], v8\nvmv.x.s %[b], v10\nvmv.x.s %[c], v18\n" \
    "li t0, " STR(VLEN/W) "\n" \
    "vsetvli t0, t0, e" STR(W) ", m1, tu, mu\n" \
    "vse" STR(W) ".v v12, (%[out])\ncsrr zero, vstart\n" \
    : [a] "=&r"(a), [b] "=&r"(b), [c] "=&r"(c) \
    : [vl] "r"((uint64_t)vl), [out] "r"(output) : "t0", "memory"); \
  uint64_t mask=UINT64_MAX >> (64-W); \
  if ((a&mask)!=((3+vl)&mask) || (b&mask)!=((3+3*vl)&mask) || \
      (c&mask)!=((8+3*vl)&mask)) { \
    printf("FAIL RCE mixed width=%u vl=%u a=%lx b=%lx c=%lx\n",W,vl,a,b,c); return 1; \
  } \
  for(unsigned i=0;i<VLEN/W;i++) { \
    uint64_t x=0; \
    for(unsigned j=0;j<W/8;j++) x|=(uint64_t)((uint8_t*)output)[i*(W/8)+j]<<(j*8); \
    if(x!=(i<vl?9:mask)) { \
      printf("FAIL RCE mixed vector width=%u vl=%u index=%u data=%lx\n",W,vl,i,x); return 1; \
    } \
  } \
  return 0; \
}
RUN(8)
RUN(16)
RUN(32)
RUN(64)
int main(void) {
  int (*runs[])(unsigned)={run8,run16,run32,run64};
  unsigned count=0;
  for(unsigned repeat=0;repeat<3;repeat++)
    for(unsigned w=0;w<4;w++) {
      unsigned max=VLEN/(8<<w);
      unsigned lengths[]={1,3,4,5,7,8,15,max-1,max};
      for(unsigned n=0;n<sizeof(lengths)/sizeof(lengths[0]);n++) {
        if(runs[w](lengths[n])) return 1;
        count++;
      }
    }
  printf("RCE mixed PASS: %u sequences, full vector/tail checks\n",count);
  return 0;
}
