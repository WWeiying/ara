#include <stdint.h>

#include "printf.h"
#include "runtime.h"

int main(void) {
  uint64_t result;

  asm volatile(
      "li t0, 32\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      "vmv.v.i v1, 1\n"
      "vmv.v.i v2, 0\n"
      // Drain vector setup before opening the measured region.
      "vmv.x.s t1, v2\n"
      "fence\n"
      "rdcycle zero\n"
      "vredsum.vs v4,  v1, v2\n"
      "vredsum.vs v5,  v1, v2\n"
      "vredsum.vs v6,  v1, v2\n"
      "vredsum.vs v7,  v1, v2\n"
      "vredsum.vs v8,  v1, v2\n"
      "vredsum.vs v9,  v1, v2\n"
      "vredsum.vs v10, v1, v2\n"
      "vredsum.vs v11, v1, v2\n"
      "vredsum.vs v12, v1, v2\n"
      "vredsum.vs v13, v1, v2\n"
      "vredsum.vs v14, v1, v2\n"
      "vredsum.vs v15, v1, v2\n"
      "vredsum.vs v16, v1, v2\n"
      "vredsum.vs v17, v1, v2\n"
      "vredsum.vs v18, v1, v2\n"
      "vredsum.vs v19, v1, v2\n"
      // Reading the final destination closes the measured vector interval only
      // after all program-ordered reductions have retired.
      "vmv.x.s t1, v19\n"
      "fence\n"
      "rdcycle zero\n"
      "li t2, 0\n"
      "li t4, 32\n"
      "vmv.x.s t3, v4\n  xor t3, t3, t4\n  or t2, t2, t3\n"
      "vmv.x.s t3, v5\n  xor t3, t3, t4\n  or t2, t2, t3\n"
      "vmv.x.s t3, v6\n  xor t3, t3, t4\n  or t2, t2, t3\n"
      "vmv.x.s t3, v7\n  xor t3, t3, t4\n  or t2, t2, t3\n"
      "vmv.x.s t3, v8\n  xor t3, t3, t4\n  or t2, t2, t3\n"
      "vmv.x.s t3, v9\n  xor t3, t3, t4\n  or t2, t2, t3\n"
      "vmv.x.s t3, v10\n xor t3, t3, t4\n  or t2, t2, t3\n"
      "vmv.x.s t3, v11\n xor t3, t3, t4\n  or t2, t2, t3\n"
      "vmv.x.s t3, v12\n xor t3, t3, t4\n  or t2, t2, t3\n"
      "vmv.x.s t3, v13\n xor t3, t3, t4\n  or t2, t2, t3\n"
      "vmv.x.s t3, v14\n xor t3, t3, t4\n  or t2, t2, t3\n"
      "vmv.x.s t3, v15\n xor t3, t3, t4\n  or t2, t2, t3\n"
      "vmv.x.s t3, v16\n xor t3, t3, t4\n  or t2, t2, t3\n"
      "vmv.x.s t3, v17\n xor t3, t3, t4\n  or t2, t2, t3\n"
      "vmv.x.s t3, v18\n xor t3, t3, t4\n  or t2, t2, t3\n"
      "vmv.x.s t3, v19\n xor t3, t3, t4\n  or t2, t2, t3\n"
      "mv %[result], t2\n"
      : [result] "=&r"(result)
      :
      : "t0", "t1", "t2", "t3", "t4", "memory");

  const int failed = result != 0;
  printf("integer reduction throughput probe: result=%lx (%s)\n", result,
         failed ? "FAILED" : "PASSED");
  return failed;
}
