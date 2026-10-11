// SPDX-License-Identifier: Apache-2.0
// Reduction scalar seed/destination registers need not be LMUL-aligned.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"

int main(void) {
  uint64_t sum, flags;
  asm volatile(
    "vsetivli zero,1,e64,m1,tu,mu\n"
    "li t0,0x4008000000000000\nvmv.s.x v2,t0\n"
    "vsetivli zero,13,e64,m4,tu,mu\n"
    "li t0,0x3ff0000000000000\nvmv.v.x v8,t0\n"
    "csrwi fflags,0\n"
    // vs2=v8 is m4-aligned; vd=v3 and scalar vs1=v2 are legal.
    "vfredusum.vs v3,v8,v2\n"
    "vmv.x.s %[sum],v3\ncsrr %[flags],fflags\n"
    : [sum] "=&r"(sum),[flags] "=&r"(flags) :: "t0","memory");
  if(sum!=0x4030000000000000ULL || flags) {
    printf("FAIL scalar LMUL sum=%lx flags=%lx expected=16.0 flags=0\n",sum,flags);
    return 1;
  }
  printf("RCE scalar LMUL PASS: e64,m4 vfredusum v3,v8,v2\n");
  return 0;
}
