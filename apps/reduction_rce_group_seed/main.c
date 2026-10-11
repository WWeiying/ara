// SPDX-License-Identifier: Apache-2.0
// A scalar reduction seed inside an older writer's register group is a RAW.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
int main(void) {
  uint64_t sum, flags;
  asm volatile(
    "li t0,49\nvsetvli zero,t0,e64,m4,tu,mu\n"
    "li t0,0x4059000000000000\nvmv.v.x v8,t0\n" // Old seed = 100.
    "li t0,0x3ff0000000000000\nvmv.v.x v16,t0\nvmv.v.x v24,t0\n"
    "li t0,0x3fe0000000000000\nvmv.v.x v20,t0\n"
    "csrwi fflags,0\n"
    "vfdiv.vv v8,v16,v20\n" // New group v8..v11 = 2, including v10[0].
    "vfredusum.vs v3,v24,v10\n"
    "vmv.x.s %[sum],v3\ncsrr %[flags],fflags\n"
    : [sum] "=&r"(sum),[flags] "=&r"(flags) :: "t0","memory");
  if(sum!=0x4049800000000000ULL || flags) { // 49 + 2 = 51, not 149.
    printf("FAIL group seed sum=%lx expected=4049800000000000 flags=%lx\n",sum,flags);
    return 1;
  }
  printf("RCE group seed PASS: m4 producer v8..v11 -> scalar seed v10\n");
  return 0;
}
