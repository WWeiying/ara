// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint64_t input[16] __attribute__((aligned(128)));
static uint16_t mask __attribute__((aligned(128)));
static unsigned checks;
static int run(unsigned vl,unsigned active,unsigned rm,uint64_t seed,
               uint64_t a,uint64_t b,uint64_t c,uint64_t d,
               uint64_t expected,unsigned expected_flags) {
  for(unsigned i=0;i<16;i++) input[i]=0;
  input[0]=a;input[1]=b;input[2]=c;input[3]=d;mask=active;
  uint64_t result,flags;
  asm volatile(
    "vsetvli t0,zero,e64,m1,tu,mu\n"
    "vle64.v v4,(%[in])\nvmv.v.x v2,%[seed]\n"
    "li t0,0x5a5a5a5a5a5a5a5a\nvmv.v.x v8,t0\n"
    "vsetvli t0,%[vl],e64,m1,tu,mu\nvlm.v v0,(%[mask])\n"
    "csrw frm,%[rm]\ncsrwi fflags,0\n"
    "vfredusum.vs v8,v4,v2,v0.t\nvmv.x.s %[result],v8\ncsrr %[flags],fflags\n"
    : [result] "=&r"(result),[flags] "=&r"(flags)
    : [in] "r"(input),[mask] "r"(&mask),[seed] "r"(seed),
      [vl] "r"((uint64_t)vl),[rm] "r"((uint64_t)rm) : "t0","memory");
  checks++;
  if(result!=expected || flags!=expected_flags) {
    printf("FAIL FP64 edge case=%u vl=%u mask=%x rm=%u got=%lx flags=%lx expected=%lx/%x\n",
      checks,vl,active,rm,result,flags,expected,expected_flags);return 1;
  }
  return 0;
}
int main(void) {
  const uint64_t one=0x3ff0000000000000ULL,inf=0x7ff0000000000000ULL;
  const uint64_t sign=0x8000000000000000ULL,nan=0x7ff8000000000000ULL;
  for(unsigned rm=0;rm<5;rm++) {
    if(run(1,1,rm,one,one,0,0,0,0x4000000000000000ULL,0) ||
       run(4,8,rm,one,inf|1,inf|1,inf|1,one,0x4000000000000000ULL,0) ||
       run(4,8,rm,inf|1,0,0,0,one,nan,16) ||
       run(4,0,rm,inf|1,inf|1,inf,sign|inf,one,inf|1,0) ||
       run(0,0,rm,inf|1,0,0,0,0,0x5a5a5a5a5a5a5a5aULL,0) ||
       run(4,15,rm,sign,sign,sign,sign,sign,sign,0) ||
       run(4,15,rm,0,sign,sign,sign,sign,rm==2?sign:0,0) ||
       run(2,3,rm,0,inf,sign|inf,0,0,nan,16) ||
       run(2,2,rm,0,0,inf|1,0,0,nan,16) ||
       run(2,2,rm,0,0,nan|0x123,0,0,nan,0) ||
       run(2,3,rm,0,inf-1,inf-1,0,0,(rm==1||rm==2)?inf-1:inf,5) ||
       run(2,2,rm,one,0,0x3ca0000000000000ULL,0,0,one+(rm>=3),1) ||
       run(2,3,rm,0,1,1,0,0,2,0) ||
       run(2,3,rm,0,0x000fffffffffffffULL,1,0,0,0x0010000000000000ULL,0)) return 1;
  }
  printf("RCE FP64 edges PASS: %u cases, FRM/NaN/Inf/zero/Mask/VL0/empty lanes\n",checks);return 0;
}
