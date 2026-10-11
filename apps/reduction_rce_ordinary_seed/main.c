// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
#define INT_CASE(LMUL,N) do { \
  uint64_t got,masked,begin,end; \
  asm volatile("li t0," #N "\nvsetvli zero,t0,e64,m" #LMUL ",tu,mu\n" \
    "vmv.v.i v4,1\nvmv.v.i v20,2\nvmv.v.i v12,1\ncsrr zero,vstart\n" \
    "rdcycle %[begin]\n.rept 32\nvadd.vv v8,v4,v20\nvredsum.vs v16,v12,v8\n.endr\n" \
    "vmv.x.s %[got],v16\nrdcycle %[end]\n" \
    "vmv.v.i v8,7\nvmclr.m v0\nvadd.vv v8,v4,v20,v0.t\nvredsum.vs v16,v12,v8\n" \
    "vmv.x.s %[masked],v16\n" \
    : [got] "=&r"(got),[masked] "=&r"(masked),[begin] "=&r"(begin),[end] "=&r"(end) \
    :: "t0","memory"); \
  if(got!=(N)+3 || masked!=(N)+7) {printf("FAIL ordinary integer m" #LMUL " got=%lu masked=%lu\n",got,masked);return 1;} \
  printf("ORDINARY_SEED integer m" #LMUL " cycles=%lu\n",end-begin); \
}while(0)
int main(void) {
  asm volatile("vsetvli t0,zero,e8,m8,tu,mu\nvmv.v.i v0,0\nvmv.v.i v8,0\nvmv.v.i v16,0\nvmv.v.i v24,0\n" ::: "t0","memory");
  INT_CASE(1,16); INT_CASE(2,32); INT_CASE(4,64);
  uint64_t got,flags,begin,end;
  asm volatile("li t0,16\nvsetvli zero,t0,e64,m1,tu,mu\n"
    "vmv.v.x v4,%[one]\nvmv.v.x v20,%[two]\nvmv.v.x v12,%[one]\ncsrw fflags,zero\ncsrr zero,vstart\n"
    "rdcycle %[begin]\n.rept 32\nvfadd.vv v8,v4,v20\nvfredusum.vs v16,v12,v8\n.endr\n"
    "vmv.x.s %[got],v16\ncsrr %[flags],fflags\nrdcycle %[end]\n"
    : [got] "=&r"(got),[flags] "=&r"(flags),[begin] "=&r"(begin),[end] "=&r"(end)
    : [one] "r"(0x3ff0000000000000ULL),[two] "r"(0x4000000000000000ULL) : "t0","memory");
  if(got!=0x4033000000000000ULL || flags){printf("FAIL ordinary float got=%lx flags=%lu\n",got,flags);return 2;}
  printf("ORDINARY_SEED float cycles=%lu\n",end-begin);
  // Different VFU producer: bitwise OR constructs the FP seed bit pattern.
  asm volatile("vmv.v.i v20,0\n.rept 32\nvor.vv v8,v4,v20\nvfredmax.vs v16,v12,v8\n.endr\n"
    "vmv.x.s %[got],v16\n" : [got] "=&r"(got) :: "memory");
  if(got!=0x3ff0000000000000ULL)return 3;
  asm volatile("li t0,64\nvsetvli zero,t0,e64,m4,tu,mu\n"
    "vmv.v.x v0,%[one]\nvmv.v.x v16,%[three]\nvmv.v.i v24,0\ncsrr zero,vstart\n"
    "rdcycle %[begin]\n.rept 16\nvor.vv v8,v16,v24\nvfredmax.vs v4,v0,v8\n.endr\n"
    "vmv.x.s %[got],v4\nrdcycle %[end]\n"
    : [got] "=&r"(got),[begin] "=&r"(begin),[end] "=&r"(end)
    : [one] "r"(0x3ff0000000000000ULL),[three] "r"(0x4008000000000000ULL) : "t0","memory");
  if(got!=0x4008000000000000ULL)return 4;
  printf("ORDINARY_SEED cross_vfu m4 cycles=%lu\n",end-begin);
  asm volatile("vmv.v.i v0,1\nvmv.v.i v16,1\nvmv.v.i v24,3\ncsrr zero,vstart\n"
    "rdcycle %[begin]\n.rept 16\nvmul.vv v8,v16,v24\nvredsum.vs v4,v0,v8\n.endr\n"
    "vmv.x.s %[got],v4\nrdcycle %[end]\n"
    : [got] "=&r"(got),[begin] "=&r"(begin),[end] "=&r"(end) :: "memory");
  if(got!=67)return 5;
  printf("ORDINARY_SEED mul_to_alu m4 cycles=%lu\n",end-begin);
  printf("PASS ordinary seed producers, LMUL and masked fallback\n");
  return 0;
}
