#include <stdint.h>

#include "printf.h"
#include "runtime.h"

int main(void) {
  uint64_t result;

  asm volatile(
      "li t0, 1\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      "vmv.v.i v2, 0\n"
      "li t1, 0x3c00\n"
      "li t0, 32\n"
      "vsetvli t0, t0, e16, m1, ta, ma\n"
      "vmv.v.x v1, t1\n"
      "vmv.x.s t2, v1\n"
      "fence\n"
      "rdcycle zero\n"
      // The widened e32 destination has EMUL=2, so each destination group
      // starts at an even-numbered architectural register.
      "vfwredosum.vs v4,  v1, v2\n"
      "vfwredosum.vs v6,  v1, v2\n"
      "vfwredosum.vs v8,  v1, v2\n"
      "vfwredosum.vs v10, v1, v2\n"
      "vfwredosum.vs v12, v1, v2\n"
      "vfwredosum.vs v14, v1, v2\n"
      "vfwredosum.vs v16, v1, v2\n"
      "vfwredosum.vs v18, v1, v2\n"
      "li t0, 1\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      "vmv.x.s t1, v18\n"
      "fence\n"
      "rdcycle zero\n"
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
      "mv %[result], t2\n"
      : [result] "=&r"(result)
      :
      : "t0", "t1", "t2", "t3", "t4", "memory");

  const int failed = result != 0;
  printf("widening ordered stream probe: result=%lx (%s)\n", result,
         failed ? "FAILED" : "PASSED");
  return failed;
}
