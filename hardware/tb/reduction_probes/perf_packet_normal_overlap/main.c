// SPDX-License-Identifier: Apache-2.0
// Independent ordinary-FPU writeback and exact reduction packet transport.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint32_t output[32] __attribute__((aligned(128)));
int main(void) {
  uint64_t vl, exact, flags;
  asm volatile(
    "li t0,32\nvsetvli %[vl],t0,e32,m1,tu,mu\n"
    "li t0,0x3f800000\nvmv.v.x v14,t0\nvmv.v.x v4,t0\n"
    "li t0,0x40000000\nvmv.v.x v16,t0\n"
    "li t0,0x40400000\nvmv.s.x v2,t0\n"
    "csrwi frm,0\ncsrwi fflags,0\ncsrr zero,vstart\n"
    "vfadd.vv v12,v14,v16\n"
    "vfredusum.vs v8,v4,v2\n"
    "vse32.v v12,(%[out])\nvmv.x.s %[exact],v8\ncsrr %[flags],fflags\n"
    : [vl] "=&r"(vl), [exact] "=&r"(exact), [flags] "=&r"(flags)
    : [out] "r"(output) : "t0", "memory");
  unsigned failed=vl!=32 || (uint32_t)exact!=0x420c0000U || flags!=0;
  for(unsigned i=0;i<32;i++) if(output[i]!=0x40400000U) {
    failed++;
    printf("PACKET_NORMAL_ELEMENT_FAIL index=%u got=%x expected=40400000\n",i,output[i]);
  }
  printf("PACKET_NORMAL_DRAIN_DONE vl=%lu checked=32 exact=%lx expected=420c0000 flags=%lx %s\n",
         vl,exact,flags,failed?"FAIL":"PASS");
  return failed;
}
