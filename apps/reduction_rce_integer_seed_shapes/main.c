// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
int main(void) {
  uint64_t a,b,c,d,e;
  asm volatile(
    "li t0,32\nvsetvli zero,t0,e32,m1,tu,mu\n"
    "vmv.v.i v2,3\nvmv.v.i v4,-1\nvmv.v.i v6,5\n"
    "vredsum.vs v8,v4,v2\nvredmax.vs v10,v6,v8\nvmv.x.s %[a],v10\n"
    "vmv.v.i v4,1\nvredsum.vs v8,v4,v2\n"
    "vsetivli zero,1,e32,m1,tu,mu\nvredxor.vs v10,v6,v8\nvmv.x.s %[b],v10\n"
    "li t0,32\nvsetvli zero,t0,e32,m1,tu,mu\nvmv.v.i v0,0\n"
    "vredsum.vs v8,v4,v2\nvsetivli zero,1,e32,m1,tu,mu\n"
    "vredmin.vs v10,v6,v8,v0.t\nvmv.x.s %[c],v10\n"
    "li t0,99\nvmv.s.x v10,t0\n"
    "vredsum.vs v8,v4,v2\nvsetivli zero,0,e32,m1,tu,mu\n"
    "vredsum.vs v10,v6,v8\nvsetivli zero,1,e32,m1,tu,mu\nvmv.x.s %[d],v10\n"
    // A 32-bit producer cannot supply the pre-existing upper 32 bits of a
    // 64-bit seed. This legal chain must retain the normal VRF seed read.
    "vsetivli zero,16,e64,m1,tu,mu\nvmv.v.x v8,%[canary]\n"
    "vsetivli zero,13,e32,m1,tu,mu\nvmv.v.i v4,1\nvmv.v.i v2,3\n"
    "vredsum.vs v8,v4,v2\nvsetivli zero,5,e64,m1,tu,mu\nvmv.v.i v6,2\n"
    "vredsum.vs v10,v6,v8\nvmv.x.s %[e],v10\n"
    : [a] "=&r"(a),[b] "=&r"(b),[c] "=&r"(c),[d] "=&r"(d),[e] "=&r"(e)
    : [canary] "r"(0x1122334400000005ULL) : "t0","memory");
  if(a!=5 || b!=38 || c!=35 || d!=99 || e!=0x112233440000001aULL) {
    printf("FAIL integer seed shapes opcode=%lx vl1=%lx mask=%lx vl0=%lx wide_seed=%lx\n",a,b,c,d,e);return 1;
  }
  printf("RCE integer seed shapes PASS: mixed opcode/VL, empty lanes, all Mask, VL0, wider-seed fallback\n");
  return 0;
}
