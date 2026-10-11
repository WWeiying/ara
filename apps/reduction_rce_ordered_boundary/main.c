// SPDX-License-Identifier: Apache-2.0
// Exact sum retains 1; strictly ordered FP32 sum loses it before cancellation.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static const uint32_t input[32] __attribute__((aligned(128))) =
  {0x60ad78ec,0x3f800000,0xe0ad78ec};
static uint32_t output[32] __attribute__((aligned(128)));
int main(void) {
  uint64_t exact0,ordered,exact1,flags;
  asm volatile(
    "li t0,3\nvsetvli t0,t0,e32,m1,tu,mu\n"
    "vle32.v v4,(%[in])\nvmv.v.i v2,0\n"
    "li t0,0x3f800000\nvmv.v.x v6,t0\n"
    "csrwi frm,0\ncsrwi fflags,0\n"
    "vfredusum.vs v8,v4,v2\n"
    "vfredosum.vs v10,v4,v2\n"
    "vfadd.vv v16,v6,v6\n"
    "vfredusum.vs v12,v4,v2\n"
    "vmv.x.s %[a],v8\nvmv.x.s %[b],v10\nvmv.x.s %[c],v12\n"
    "vse32.v v16,(%[out])\ncsrr %[flags],fflags\ncsrr zero,vstart\n"
    : [a] "=&r"(exact0),[b] "=&r"(ordered),[c] "=&r"(exact1),[flags] "=&r"(flags)
    : [in] "r"(input),[out] "r"(output) : "t0","memory");
  if(exact0!=0x3f800000 || ordered!=0 || exact1!=0x3f800000 || flags!=1) {
    printf("FAIL RCE ordered boundary exact=%lx/%lx ordered=%lx flags=%lx\n",exact0,exact1,ordered,flags);return 1;
  }
  for(unsigned i=0;i<3;i++) if(output[i]!=0x40000000) {
    printf("FAIL RCE ordered boundary add[%u]=%x\n",i,output[i]);return 1;
  }
  printf("RCE ordered boundary PASS: exact=1, ordered=0, NX=1, empty lane\n");return 0;
}
