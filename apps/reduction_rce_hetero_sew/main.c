// SPDX-License-Identifier: Apache-2.0
// Pre-layout independent operands, then change SEW/VL/backend without a drain.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"

int main(void) {
  uint64_t a,b,c,d,flags;
  asm volatile(
    "li t0,32\nvsetvli zero,t0,e8,m1,tu,mu\n"
    "vmv.v.i v4,1\nvmv.v.i v20,3\nli t0,0x55\nvmv.v.x v0,t0\n"
    "vsetivli zero,9,e16,m1,tu,mu\nvmv.v.i v6,2\nvmv.v.i v22,5\n"
    "vsetivli zero,3,e32,m1,tu,mu\nvmv.v.i v14,3\nvmv.v.i v24,7\n"
    "vsetivli zero,1,e64,m1,tu,mu\nvmv.v.i v16,4\nvmv.v.i v26,11\n"
    "vsetivli zero,31,e8,m1,tu,mu\nvredsum.vs v8,v4,v20,v0.t\n"
    "vsetivli zero,9,e16,m1,tu,mu\nvredxor.vs v10,v6,v22\n"
    "vsetivli zero,3,e32,m1,tu,mu\nvredmax.vs v12,v14,v24\n"
    "vsetivli zero,1,e64,m1,tu,mu\nvredmin.vs v18,v16,v26\n"
    "vmv.x.s %[d],v18\n"
    "vsetivli zero,1,e8,m1,tu,mu\nvmv.x.s %[a],v8\n"
    "vsetivli zero,1,e16,m1,tu,mu\nvmv.x.s %[b],v10\n"
    "vsetivli zero,1,e32,m1,tu,mu\nvmv.x.s %[c],v12\n"
    : [a] "=&r"(a),[b] "=&r"(b),[c] "=&r"(c),[d] "=&r"(d)
    : : "t0","memory");
  // 16 unmasked ones + 3; nine copies of 2 XOR 5; max(7,3); min(11,4).
  if(a!=19 || b!=7 || c!=7 || d!=4) {
    printf("FAIL hetero integer SEW results=%lx/%lx/%lx/%lx\n",a,b,c,d);return 1;
  }
  asm volatile(
    "vsetivli zero,15,e16,m1,tu,mu\n"
    "li t0,0x3c00\nvmv.v.x v4,t0\nli t0,0x4000\nvmv.v.x v20,t0\n"
    "vsetivli zero,9,e32,m1,tu,mu\n"
    "li t0,0x3f800000\nvmv.v.x v6,t0\n"
    "li t0,0x40000000\nvmv.v.x v22,t0\nvmv.v.x v26,t0\n"
    "vsetivli zero,3,e64,m1,tu,mu\n"
    "li t0,0x3ff0000000000000\nvmv.v.x v14,t0\n"
    "li t0,0x4000000000000000\nvmv.v.x v24,t0\ncsrwi fflags,0\n"
    "vsetivli zero,15,e16,m1,tu,mu\nvfredmin.vs v8,v4,v20,v0.t\n"
    "vsetivli zero,9,e32,m1,tu,mu\nvfredusum.vs v10,v6,v22\n"
    "vsetivli zero,3,e64,m1,tu,mu\nvfredusum.vs v12,v14,v24\n"
    "vsetivli zero,7,e16,m1,tu,mu\nvfwredusum.vs v18,v4,v26,v0.t\n"
    "vsetivli zero,1,e16,m1,tu,mu\nvmv.x.s %[a],v8\n"
    "vsetivli zero,1,e32,m1,tu,mu\nvmv.x.s %[b],v10\nvmv.x.s %[d],v18\n"
    "vsetivli zero,1,e64,m1,tu,mu\nvmv.x.s %[c],v12\ncsrr %[flags],fflags\n"
    : [a] "=&r"(a),[b] "=&r"(b),[c] "=&r"(c),[d] "=&r"(d),[flags] "=&r"(flags)
    : : "t0","memory");
  // min(2,1), 2+9, 2+3, 2+four active FP16 ones, all exactly representable.
  if(a!=0x3c00 || b!=0x41300000 || c!=0x4014000000000000ULL ||
     d!=0x40c00000 || flags) {
    printf("FAIL hetero FP SEW results=%lx/%lx/%lx/%lx flags=%lx\n",a,b,c,d,flags);return 1;
  }
  printf("RCE heterogeneous SEW PASS: 8 integer/minmax/exact/FP64 results, mixed VL/Mask\n");
  return 0;
}
