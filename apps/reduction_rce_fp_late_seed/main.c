// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
#define EXTREMES(W,ONE,FOUR,SNAN,MASK) do { \
  uint64_t got,flags,begin,end; \
  asm volatile("li t0,16\nvsetvli zero,t0,e" #W ",m1,tu,mu\n" \
    "vmv.v.x v4,%[one]\nvmv.v.x v6,%[four]\nvmv.v.x v8,%[one]\n" \
    "csrw fflags,zero\ncsrr zero,vstart\nrdcycle %[begin]\n" \
    ".rept 32\nvfredmax.vs v8,v6,v8\nvfredmin.vs v8,v4,v8\n.endr\n" \
    "vmv.x.s %[got],v8\ncsrr %[flags],fflags\nrdcycle %[end]\n" \
    : [got] "=&r"(got),[flags] "=&r"(flags),[begin] "=&r"(begin),[end] "=&r"(end) \
    : [one] "r"((uint64_t)(ONE)), [four] "r"((uint64_t)(FOUR)) : "t0","memory"); \
  if((got & (MASK)) != (ONE) || flags) return 1; \
  printf("FP_LATE extremes e" #W " cycles=%lu\n",end-begin); \
  asm volatile("vmv.v.x v8,%[seed]\nvmclr.m v0\ncsrw fflags,zero\n" \
    ".rept 16\nvfredmax.vs v8,v6,v8,v0.t\nvfredmin.vs v8,v4,v8,v0.t\n.endr\n" \
    "vmv.x.s %[got],v8\ncsrr %[flags],fflags\n" \
    : [got] "=&r"(got),[flags] "=&r"(flags) : [seed] "r"((uint64_t)(SNAN)) : "memory"); \
  if((got & (MASK)) != (SNAN) || flags) return 2; \
} while(0)
int main(void) {
  asm volatile("vsetvli t0,zero,e8,m8,tu,mu\nvmv.v.i v0,0\nvmv.v.i v8,0\nvmv.v.i v16,0\nvmv.v.i v24,0\n" ::: "t0","memory");
  EXTREMES(16,0x3c00ULL,0x4400ULL,0x7c01ULL,0xffffULL);
  EXTREMES(32,0x3f800000ULL,0x40800000ULL,0x7f800001ULL,0xffffffffULL);
  EXTREMES(64,0x3ff0000000000000ULL,0x4010000000000000ULL,0x7ff0000000000001ULL,~0ULL);
  uint64_t got,flags,begin,end;
  asm volatile("li t0,16\nvsetvli zero,t0,e64,m1,tu,mu\n"
    "vmv.v.x v4,%[one]\nvmv.v.x v8,%[three]\ncsrw fflags,zero\ncsrr zero,vstart\n"
    "rdcycle %[begin]\n.rept 32\nvfredusum.vs v8,v4,v8\n.endr\n"
    "vmv.x.s %[got],v8\ncsrr %[flags],fflags\nrdcycle %[end]\n"
    : [got] "=&r"(got),[flags] "=&r"(flags),[begin] "=&r"(begin),[end] "=&r"(end)
    : [one] "r"(0x3ff0000000000000ULL),[three] "r"(0x4008000000000000ULL) : "t0","memory");
  if(got != 0x4080180000000000ULL || flags) {printf("FAIL FP64 late got=%lx flags=%lu\n",got,flags);return 3;}
  printf("FP_LATE sum64 cycles=%lu\nPASS FP late seed chains\n",end-begin);
  return 0;
}
