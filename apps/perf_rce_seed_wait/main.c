// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include "printf.h"
#include "runtime.h"

int main(void) {
  uint64_t dependent, independent, begin, end;
  const uint64_t dividend = UINT64_C(0x7fffffffffffffff);
  asm volatile(
    "vsetvli t0,zero,e8,m8,tu,mu\n"
    "vmv.v.i v0,0\nvmv.v.i v8,0\nvmv.v.i v16,0\nvmv.v.i v24,0\n"
    "vsetivli zero,16,e64,m1,tu,mu\n"
    "vmv.v.i v0,1\nvmv.v.x v16,%[dividend]\n"
    "vmv.v.i v24,7\nvmv.v.i v20,5\ncsrr zero,vstart\n"
    "rdcycle %[begin]\n"
    ".rept 16\n"
    // One divide per lane; its seed is delayed while the VALU reduces sources.
    "vsetivli zero,4,e64,m1,tu,mu\n"
    "vdivu.vv v8,v16,v24\n"
    "vsetivli zero,16,e64,m1,tu,mu\n"
    "vredsum.vs v4,v0,v8\n"
    "vredsum.vs v12,v0,v20\n"
    // Check both outputs on each iteration; extraction is outside the overlap.
#ifdef RCE_SEED_WAIT_CONSUMER_FIRST
    "vadd.vv v28,v12,v0\n"
    "vmv.x.s %[independent],v28\n"
    "addi %[independent],%[independent],-1\n"
    "vmv.x.s %[dependent],v4\n"
#else
    "vmv.x.s %[dependent],v4\n"
    "vmv.x.s %[independent],v12\n"
#endif
    "bne %[dependent],%[expected],1f\n"
    "bne %[independent],%[twentyone],1f\n"
    ".endr\n"
    "1: rdcycle %[end]\n"
    : [dependent] "=&r"(dependent), [independent] "=&r"(independent),
      [begin] "=&r"(begin), [end] "=&r"(end)
    : [dividend] "r"(dividend), [expected] "r"(dividend / 7 + 16),
      [twentyone] "r"(UINT64_C(21))
    : "t0", "memory");
  if (dependent != dividend / 7 + 16 || independent != 21) {
    printf("FAIL seed wait dependent=%lx independent=%lx\n", dependent, independent);
    return 1;
  }
#ifdef RCE_SEED_WAIT_CONSUMER_FIRST
  printf("RCE seed wait consumer probe PASS: pairs=16 cycles=%lu\n", end - begin);
#else
  printf("RCE seed wait probe PASS: pairs=16 cycles=%lu\n", end - begin);
#endif
  return 0;
}
