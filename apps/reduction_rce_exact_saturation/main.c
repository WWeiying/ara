// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static const uint8_t mask[4] __attribute__((aligned(128)))={0,255,0,0};
static uint32_t output[32] __attribute__((aligned(128)));
int main(void) {
 uint64_t sum,sat;
 asm volatile(
   "li t0,32\nvsetvli t0,t0,e32,m1,tu,mu\n"
   "li t0,0x3f800000\nvmv.v.x v4,t0\n"
   "li t0,0x40400000\nvmv.v.x v2,t0\n"
   "li t0,0x80000000\nvmv.v.x v14,t0\nvmv.v.i v12,0\n"
   "vlm.v v0,(%[mask])\ncsrwi vxsat,0\n"
   "vfredusum.vs v8,v4,v2\n"
   "vsmul.vv v12,v14,v14,v0.t\n"
   "csrr %[sat],vxsat\nvmv.x.s %[sum],v8\n"
   "vse32.v v12,(%[out])\ncsrr zero,vstart\n"
   : [sum] "=&r"(sum),[sat] "=&r"(sat)
   : [mask] "r"(mask),[out] "r"(output) : "t0","memory");
 if(sum!=0x420c0000 || sat!=1) {
   printf("FAIL exact RCE saturation sum=%lx sat=%lu\n",sum,sat);return 1;
 }
 for(unsigned i=0;i<32;i++) if(output[i]!=((i>=8&&i<16)?0x7fffffff:0)) {
   printf("FAIL exact RCE saturation i=%u value=%x\n",i,output[i]);return 1;
 }
 printf("RCE exact saturation PASS: masked VSMUL result and flag\n");return 0;
}
