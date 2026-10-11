// SPDX-License-Identifier: Apache-2.0
// Narrow packing into a just-dequeued slot must not retain old data or flags.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint64_t wide[32] __attribute__((aligned(128)));
static uint32_t a[32] __attribute__((aligned(128)));
static uint32_t b[32] __attribute__((aligned(128)));
static uint32_t out[3][32] __attribute__((aligned(128)));
static uint64_t fp_bits(unsigned n,unsigned bits) {
  unsigned e=0;for(unsigned x=n;x>1;x>>=1)++e;
  unsigned f=bits==64?52:23,bias=bits==64?1023:127;
  return ((uint64_t)(bias+e)<<f)|((uint64_t)(n-(1U<<e))<<(f-e));
}
static int integer_case(unsigned vl) {
  uint64_t sum,sat;
  for(unsigned i=0;i<32;i++) {
    wide[i]=i%3==0 ? 0x100000008ULL+i*16 : 0x800000ULL+i*80;
    a[i]=0x10203040U+i*0x10203U;b[i]=0x40800001U-i*0x103U;
    for(unsigned j=0;j<3;j++)out[j][i]=0xdecafbad;
  }
  asm volatile(
    "vsetvli zero,%[vl],e32,m1,tu,mu\n"
    "vle64.v v24,(%[src])\nvle32.v v14,(%[a])\nvle32.v v16,(%[b])\n"
    "vmv.v.i v4,1\nvmv.v.i v2,3\ncsrwi vxsat,0\ncsrwi vxrm,2\n"
    "li t1,8\n1:\n"
    "vredsum.vs v8,v4,v2\n"
    "vnclipu.wi v12,v24,0\n"
    "vadd.vv v18,v14,v16\n"
    "vnsrl.wi v20,v24,4\n"
    "addi t1,t1,-1\nbnez t1,1b\n"
    "vmv.x.s %[sum],v8\ncsrr %[sat],vxsat\n"
    "vse32.v v12,(%[o0])\nvse32.v v18,(%[o1])\nvse32.v v20,(%[o2])\ncsrr zero,vstart\n"
    : [sum] "=&r"(sum),[sat] "=&r"(sat)
    : [vl] "r"((uint64_t)vl),[src] "r"(wide),[a] "r"(a),[b] "r"(b),
      [o0] "r"(out[0]),[o1] "r"(out[1]),[o2] "r"(out[2]) : "t1","memory");
  if(sum!=vl+3 || sat!=1) {printf("FAIL recycle integer scalar vl=%u sum=%lx sat=%lx\n",vl,sum,sat);return 1;}
  for(unsigned i=0;i<32;i++) {
    uint32_t exp[3]={wide[i]>0xffffffffULL?0xffffffffU:(uint32_t)wide[i],a[i]+b[i],(uint32_t)(wide[i]>>4)};
    for(unsigned j=0;j<3;j++)if(out[j][i]!=(i<vl?exp[j]:0xdecafbadU)) {
      printf("FAIL recycle integer vl=%u stream=%u i=%u got=%x expected=%x\n",vl,j,i,out[j][i],i<vl?exp[j]:0xdecafbadU);return 1;
    }
  }
  return 0;
}
static int float_case(unsigned vl) {
  uint64_t sum,flags;
  for(unsigned i=0;i<32;i++) {
    wide[i]=fp_bits(i+1,64);a[i]=(uint32_t)fp_bits(i+1,32);b[i]=0x40000000;
    for(unsigned j=0;j<3;j++)out[j][i]=0xdecafbad;
  }
  asm volatile(
    "vsetvli zero,%[vl],e32,m1,tu,mu\n"
    "vle64.v v24,(%[src])\nvle32.v v14,(%[a])\nvle32.v v16,(%[b])\n"
    "li t0,0x3f800000\nvmv.v.x v4,t0\nli t0,0x40400000\nvmv.v.x v2,t0\n"
    "csrwi fflags,0\nli t1,8\n1:\n"
    "vfredusum.vs v8,v4,v2\n"
    "vfncvt.f.f.w v12,v24\n"
    "vfadd.vv v18,v14,v16\n"
    "vfmul.vv v20,v14,v16\n"
    "addi t1,t1,-1\nbnez t1,1b\n"
    "vmv.x.s %[sum],v8\ncsrr %[flags],fflags\n"
    "vse32.v v12,(%[o0])\nvse32.v v18,(%[o1])\nvse32.v v20,(%[o2])\ncsrr zero,vstart\n"
    : [sum] "=&r"(sum),[flags] "=&r"(flags)
    : [vl] "r"((uint64_t)vl),[src] "r"(wide),[a] "r"(a),[b] "r"(b),
      [o0] "r"(out[0]),[o1] "r"(out[1]),[o2] "r"(out[2]) : "t0","t1","memory");
  if((uint32_t)sum!=fp_bits(vl+3,32) || flags) {printf("FAIL recycle FP scalar vl=%u sum=%lx flags=%lx\n",vl,sum,flags);return 1;}
  for(unsigned i=0;i<32;i++) {
    uint32_t exp[3]={(uint32_t)fp_bits(i+1,32),(uint32_t)fp_bits(i+3,32),(uint32_t)fp_bits(2*(i+1),32)};
    for(unsigned j=0;j<3;j++)if(out[j][i]!=(i<vl?exp[j]:0xdecafbadU)) {
      printf("FAIL recycle FP vl=%u stream=%u i=%u got=%x expected=%x\n",vl,j,i,out[j][i],i<vl?exp[j]:0xdecafbadU);return 1;
    }
  }
  return 0;
}
int main(void) {
  unsigned lengths[]={1,7,16,31,32};
  for(unsigned n=0;n<5;n++)if(integer_case(lengths[n])||float_case(lengths[n]))return 1;
  printf("RCE queue recycle PASS: 10 sequences, integer/FP narrowing, distinct words, saturation and store sentinels\n");return 0;
}
