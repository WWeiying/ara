#include <stdint.h>

#include "printf.h"
#include "runtime.h"

int main(void) {
  uint64_t mismatch;
  asm volatile(
      "li t0, 16\n"
      "vsetvli t0, t0, e64, m1, ta, ma\n"
      "li t1, 0x3ff0000000000000\n"
      "vmv.v.x v1, t1\n"
      "vmv.v.i v2, 0\n"
      "vmv.x.s t1, v1\n"
      "fence\n"
      "rdcycle zero\n"
      "vfredosum.vs v4,  v1, v2\n"
      "vfredosum.vs v5,  v1, v2\n"
      "vfredosum.vs v6,  v1, v2\n"
      "vfredosum.vs v7,  v1, v2\n"
      "vfredosum.vs v8,  v1, v2\n"
      "vfredosum.vs v9,  v1, v2\n"
      "vfredosum.vs v10, v1, v2\n"
      "vfredosum.vs v11, v1, v2\n"
      "vmv.x.s t1, v11\n"
      "fence\n"
      "rdcycle zero\n"
      // Keep one unordered e64 operation outside the measured window.  The
      // ordered-fast slice is optimized below, while unordered e64 must
      // continue to use the proven legacy path without entering the e16/e32
      // context DAG.
      "vfredusum.vs v12, v1, v2\n"
      "li t2, 0\n"
      "li t4, 0x4030000000000000\n"
      "vmv.x.s t3, v12\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
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
      "vmv.x.s t3, v8\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      "vmv.x.s t3, v9\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      "vmv.x.s t3, v10\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      "vmv.x.s t3, v11\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      "mv %[mismatch], t2\n"
      : [mismatch] "=&r"(mismatch)
      :
      : "t0", "t1", "t2", "t3", "t4", "memory");

  const int failed = mismatch != 0;
  printf("e64 ordered reduction stream probe: mismatch=%lx (%s)\n", mismatch,
         failed ? "FAILED" : "PASSED");
  return failed;
}
