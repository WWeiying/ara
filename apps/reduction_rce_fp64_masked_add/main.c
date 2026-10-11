// SPDX-License-Identifier: Apache-2.0
// Ordinary mask 0xff must not be interpreted as a reduction-context tag.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint8_t mask[16] __attribute__((aligned(128))) = {0xff,0xff};
static uint64_t output[16] __attribute__((aligned(128)));
int main(void) {
  uint64_t sum, flags;
  asm volatile(
    "li t0,16\nvsetvli zero,t0,e64,m1,tu,mu\n"
    "li t0,0x3ff0000000000000\nvmv.v.x v4,t0\n"
    "li t0,0x4008000000000000\nvmv.v.x v2,t0\n"
    "vmv.v.i v12,0\nvlm.v v0,(%[mask])\ncsrwi fflags,0\n"
    "vfredusum.vs v8,v4,v2\n"
    "vfadd.vv v12,v4,v4,v0.t\n"
    "vse64.v v12,(%[out])\nvmv.x.s %[sum],v8\ncsrr %[flags],fflags\n"
    : [sum] "=&r"(sum),[flags] "=&r"(flags)
    : [mask] "r"(mask),[out] "r"(output) : "t0","memory");
  if(sum!=0x4033000000000000ULL || flags) {
    printf("FAIL masked add sum=%lx flags=%lx\n",sum,flags);return 1;
  }
  for(unsigned i=0;i<16;i++) if(output[i]!=0x4000000000000000ULL) {
    printf("FAIL masked add i=%u got=%lx expected=4000000000000000\n",i,output[i]);return 1;
  }
  printf("RCE FP64 masked add PASS: full mask payload under completion overlap\n");
  return 0;
}
