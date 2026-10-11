// SPDX-License-Identifier: Apache-2.0
// Different packets have different flags; an older RCE blocks result retirement.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static const uint16_t mask __attribute__((aligned(128)))=0x00f0;
static const uint64_t mul_input[16] __attribute__((aligned(128))) =
  {0,0,0,0,0x8000000000000000ULL,0x8000000000000000ULL,
   0x8000000000000000ULL,0x8000000000000000ULL};
static uint64_t output[16] __attribute__((aligned(128)));
int main(void) {
  uint64_t sum,sat;
  asm volatile(
    "li t0,16\nvsetvli t0,t0,e64,m1,tu,mu\n"
    "li t0,0x3ff0000000000000\nvmv.v.x v4,t0\n"
    "li t0,0x4008000000000000\nvmv.v.x v2,t0\n"
    "vle64.v v14,(%[in])\nvmv.v.i v12,0\n"
    "vlm.v v0,(%[mask])\ncsrwi vxrm,0\ncsrwi vxsat,0\n"
    "vfredusum.vs v8,v4,v2\n"
    "vsmul.vv v12,v14,v14,v0.t\n"
    "csrr %[sat],vxsat\nvmv.x.s %[sum],v8\n"
    "vse64.v v12,(%[out])\ncsrr zero,vstart\n"
    : [sum] "=&r"(sum),[sat] "=&r"(sat)
    : [in] "r"(mul_input),[mask] "r"(&mask),[out] "r"(output) : "t0","memory");
  if(sum!=0x4033000000000000ULL || sat!=1) {
    printf("FAIL FP64 RCE saturation sum=%lx sat=%lu\n",sum,sat);return 1;
  }
  for(unsigned i=0;i<16;i++) if(output[i]!=((i>=4&&i<8)?0x7fffffffffffffffULL:0)) {
    printf("FAIL FP64 RCE saturation i=%u value=%lx\n",i,output[i]);return 1;
  }
  printf("RCE FP64 saturation PASS: nonuniform packet flags under completion backpressure\n");return 0;
}
