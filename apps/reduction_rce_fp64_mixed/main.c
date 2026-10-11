// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint64_t output[16] __attribute__((aligned(128)));
int main(void) {
  uint64_t sum,chain,mul,flags,wide;
  asm volatile(
    "li t0,16\nvsetvli t0,t0,e64,m1,tu,mu\n"
    "li t0,0x3ff0000000000000\nvmv.v.x v4,t0\n"
    "li t0,0x4008000000000000\nvmv.v.x v2,t0\ncsrwi fflags,0\n"
    "vfredusum.vs v8,v4,v2\n"
    "vfadd.vv v12,v4,v4\n"
    "vfmul.vv v14,v4,v4\n"
    "vfredusum.vs v10,v4,v8\n"
    "vmv.x.s %[sum],v8\nvmv.x.s %[chain],v10\nvmv.x.s %[mul],v14\n"
    "vse64.v v12,(%[out])\ncsrr %[flags],fflags\n"
    : [sum] "=&r"(sum),[chain] "=&r"(chain),[mul] "=&r"(mul),[flags] "=&r"(flags)
    : [out] "r"(output) : "t0","memory");
  if(sum!=0x4033000000000000ULL || chain!=0x4041800000000000ULL ||
      mul!=0x3ff0000000000000ULL || flags) {
    printf("FAIL FP64 mixed sum=%lx chain=%lx mul=%lx flags=%lx\n",sum,chain,mul,flags);return 1;
  }
  for(unsigned i=0;i<16;i++) if(output[i]!=0x4000000000000000ULL) {
    printf("FAIL FP64 add i=%u value=%lx\n",i,output[i]);return 1;
  }
  asm volatile(
    "li t0,32\nvsetvli t0,t0,e32,m1,tu,mu\n"
    "li t0,0x3f800000\nvmv.v.x v4,t0\n"
    "vfwredusum.vs v16,v4,v2\n"
    "li t0,1\nvsetvli t0,t0,e64,m1,tu,mu\nvmv.x.s %[wide],v16\n"
    "csrr %[flags],fflags\n"
    : [wide] "=&r"(wide),[flags] "=&r"(flags) :: "t0","memory");
  if(wide!=0x4041800000000000ULL || flags) {
    printf("FAIL FP64 widening sum=%lx flags=%lx\n",wide,flags);return 1;
  }
  printf("RCE FP64 mixed PASS: ordinary add/mul, true seed RAW, FP32 widening\n");return 0;
}
