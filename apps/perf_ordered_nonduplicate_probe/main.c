#include <stdint.h>

#include "printf.h"
#include "runtime.h"

int main(void) {
  uint64_t result;

  asm volatile(
      "li t0, 32\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      // Raw subnormal encodings make every addition exact.  Alternating
      // source and seed registers deliberately defeats source fingerprint
      // fusion while retaining simple, bit-exact expected values.
      "vmv.v.i v1, 1\n"
      "vmv.v.i v2, 2\n"
      "vmv.v.i v3, 0\n"
      "vmv.v.i v4, 1\n"
      "vmv.x.s t1, v4\n"
      "fence\n"
      "rdcycle zero\n"
      "vfredosum.vs v8,  v1, v3\n"
      "vfredosum.vs v9,  v2, v4\n"
      "vfredosum.vs v10, v1, v3\n"
      "vfredosum.vs v11, v2, v4\n"
      "vfredosum.vs v12, v1, v3\n"
      "vfredosum.vs v13, v2, v4\n"
      "vfredosum.vs v14, v1, v3\n"
      "vfredosum.vs v15, v2, v4\n"
      "vmv.x.s t1, v15\n"
      "fence\n"
      "rdcycle zero\n"
      "li t2, 0\n"
      "li t4, 32\n"
      "vmv.x.s t3, v8\n xor t3, t3, t4\n or t2, t2, t3\n"
      "vmv.x.s t3, v10\n xor t3, t3, t4\n or t2, t2, t3\n"
      "vmv.x.s t3, v12\n xor t3, t3, t4\n or t2, t2, t3\n"
      "vmv.x.s t3, v14\n xor t3, t3, t4\n or t2, t2, t3\n"
      "li t4, 65\n"
      "vmv.x.s t3, v9\n xor t3, t3, t4\n or t2, t2, t3\n"
      "vmv.x.s t3, v11\n xor t3, t3, t4\n or t2, t2, t3\n"
      "vmv.x.s t3, v13\n xor t3, t3, t4\n or t2, t2, t3\n"
      "vmv.x.s t3, v15\n xor t3, t3, t4\n or t2, t2, t3\n"
      "mv %[result], t2\n"
      : [result] "=&r"(result)
      :
      : "t0", "t1", "t2", "t3", "t4", "memory");

  const int failed = result != 0;
  printf("ordered nonduplicate probe: result=%lx (%s)\n", result,
         failed ? "FAILED" : "PASSED");
  return failed;
}
