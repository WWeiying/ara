#include <stdint.h>

#include "printf.h"
#include "runtime.h"

int main(void) {
  uint64_t mismatch;
  asm volatile(
      "li t0, 32\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      "vid.v v3\n"
      "vmsltu.vi v0, v3, 16\n"
      "li t0, 0x3f800000\n"
      "vmv.v.x v1, t0\n"
      "li t0, 0x40a00000\n"
      "vmv.v.x v2, t0\n"
      "vmv.x.s t1, v2\n"
      "fence\n"
      "rdcycle zero\n"
      "vfredosum.vs v4,  v1, v2, v0.t\n"
      "vfredosum.vs v5,  v1, v2, v0.t\n"
      "vfredosum.vs v6,  v1, v2, v0.t\n"
      "vfredosum.vs v7,  v1, v2, v0.t\n"
      "vmv.x.s t1, v7\n"
      "fence\n"
      "rdcycle zero\n"
      "li t2, 0\n"
      "li t4, 0x41a80000\n"
      "vmv.x.s t3, v4\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      "vmv.x.s t3, v5\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      "vmv.x.s t3, v6\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      "vmv.x.s t3, v7\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      "mv %[mismatch], t2\n"
      : [mismatch] "=&r"(mismatch)
      :
      : "t0", "t1", "t2", "t3", "t4", "memory");

  const int failed = mismatch != 0;
  printf("masked ordered alias probe: mismatch=%lx (%s)\n", mismatch,
         failed ? "FAILED" : "PASSED");
  return failed;
}
