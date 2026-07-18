// SPDX-License-Identifier: Apache-2.0
// Homogeneous unordered FP16->FP32 widening reduction stream.

#include <stdint.h>

#include "printf.h"
#include "runtime.h"

int main(void) {
  uint64_t mismatch;
  uint64_t masked_result_4;
  uint64_t masked_result_6;
  uint64_t masked_result_8;
  uint64_t masked_result_10;

  asm volatile(
      // The widening seed is FP32, while the 32 source elements are FP16.
      "li t0, 1\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      "vmv.v.i v2, 0\n"
      "li t0, 32\n"
      "vsetvli t0, t0, e16, m1, ta, ma\n"
      "li t1, 0x3c00\n"
      "vmv.v.x v1, t1\n"
      "fence\n"
      "rdcycle zero\n"
      "vfwredusum.vs v4,  v1, v2\n"
      "vfwredusum.vs v6,  v1, v2\n"
      "vfwredusum.vs v8,  v1, v2\n"
      "vfwredusum.vs v10, v1, v2\n"
      "vfwredusum.vs v12, v1, v2\n"
      "vfwredusum.vs v14, v1, v2\n"
      "vfwredusum.vs v16, v1, v2\n"
      "vfwredusum.vs v18, v1, v2\n"
      // Establish a true dependence on the final reduction before closing ROI.
      "li t0, 1\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      "vmv.x.s t1, v18\n"
      "fence\n"
      "rdcycle zero\n"
      // Every independent destination must contain FP32 32.0.
      "li t2, 0\n"
      "li t4, 0x42000000\n"
      "vmv.x.s t3, v4\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      "vmv.x.s t3, v6\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      "vmv.x.s t3, v8\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      "vmv.x.s t3, v10\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      "vmv.x.s t3, v12\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      "vmv.x.s t3, v14\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      "vmv.x.s t3, v16\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      "vmv.x.s t3, v18\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      // Outside the timed ROI, run a shorter all-active masked stream.  This
      // specifically exercises background MASKU credit consumption for the
      // widening exact path.
      "li t0, 32\n"
      "vsetvli t0, t0, e16, m1, ta, ma\n"
      "vmv.v.i v0, -1\n"
      "vfwredusum.vs v4,  v1, v2, v0.t\n"
      "vfwredusum.vs v6,  v1, v2, v0.t\n"
      "vfwredusum.vs v8,  v1, v2, v0.t\n"
      "vfwredusum.vs v10, v1, v2, v0.t\n"
      "li t0, 1\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      "vmv.x.s t3, v4\n"
      "mv %[masked4], t3\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      "vmv.x.s t3, v6\n"
      "mv %[masked6], t3\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      "vmv.x.s t3, v8\n"
      "mv %[masked8], t3\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      "vmv.x.s t3, v10\n"
      "mv %[masked10], t3\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      "mv %[result], t2\n"
      : [result] "=&r"(mismatch),
        [masked4] "=&r"(masked_result_4),
        [masked6] "=&r"(masked_result_6),
        [masked8] "=&r"(masked_result_8),
        [masked10] "=&r"(masked_result_10)
      :
      : "t0", "t1", "t2", "t3", "t4", "memory");

  const int failed = mismatch != 0;
  printf("global exact widening stream: mismatch=%lx masked=%lx/%lx/%lx/%lx "
         "(%s)\n",
         mismatch, masked_result_4, masked_result_6, masked_result_8,
         masked_result_10, failed ? "FAILED" : "PASSED");
  return failed;
}
