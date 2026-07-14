#include <stdint.h>

#include "printf.h"
#include "runtime.h"

int main(void) {
  uint64_t result;

  asm volatile(
      "li t0, 32\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      // All source elements are +3.0; the scalar seed is +5.0.
      "li t0, 0x40400000\n"
      "vmv.v.x v1, t0\n"
      "li t0, 0x40a00000\n"
      "vmv.v.x v2, t0\n"
      "vmv.x.s t1, v2\n"
      "fence\n"
      "rdcycle zero\n"
      "vfredmin.vs v4,  v1, v2\n"
      "vfredmin.vs v5,  v1, v2\n"
      "vfredmin.vs v6,  v1, v2\n"
      "vfredmin.vs v7,  v1, v2\n"
      "vfredmin.vs v8,  v1, v2\n"
      "vfredmin.vs v9,  v1, v2\n"
      "vfredmin.vs v10, v1, v2\n"
      "vfredmin.vs v11, v1, v2\n"
      // All source elements are -2.0; the scalar seed is -5.0.
      "li t0, 0xc0000000\n"
      "vmv.v.x v1, t0\n"
      "li t0, 0xc0a00000\n"
      "vmv.v.x v2, t0\n"
      "vfredmax.vs v12, v1, v2\n"
      "vfredmax.vs v13, v1, v2\n"
      "vfredmax.vs v14, v1, v2\n"
      "vfredmax.vs v15, v1, v2\n"
      "vfredmax.vs v16, v1, v2\n"
      "vfredmax.vs v17, v1, v2\n"
      "vfredmax.vs v18, v1, v2\n"
      "vfredmax.vs v19, v1, v2\n"
      "vmv.x.s t1, v19\n"
      "fence\n"
      "rdcycle zero\n"
      "li t2, 0\n"
      "li t4, 0x40400000\n"
      "vmv.x.s t3, v4\n xor t3, t3, t4\n or t2, t2, t3\n"
      "vmv.x.s t3, v5\n xor t3, t3, t4\n or t2, t2, t3\n"
      "vmv.x.s t3, v6\n xor t3, t3, t4\n or t2, t2, t3\n"
      "vmv.x.s t3, v7\n xor t3, t3, t4\n or t2, t2, t3\n"
      "vmv.x.s t3, v8\n xor t3, t3, t4\n or t2, t2, t3\n"
      "vmv.x.s t3, v9\n xor t3, t3, t4\n or t2, t2, t3\n"
      "vmv.x.s t3, v10\n xor t3, t3, t4\n or t2, t2, t3\n"
      "vmv.x.s t3, v11\n xor t3, t3, t4\n or t2, t2, t3\n"
      "li t4, 0xffffffffc0000000\n"
      "vmv.x.s t3, v12\n xor t3, t3, t4\n or t2, t2, t3\n"
      "vmv.x.s t3, v13\n xor t3, t3, t4\n or t2, t2, t3\n"
      "vmv.x.s t3, v14\n xor t3, t3, t4\n or t2, t2, t3\n"
      "vmv.x.s t3, v15\n xor t3, t3, t4\n or t2, t2, t3\n"
      "vmv.x.s t3, v16\n xor t3, t3, t4\n or t2, t2, t3\n"
      "vmv.x.s t3, v17\n xor t3, t3, t4\n or t2, t2, t3\n"
      "vmv.x.s t3, v18\n xor t3, t3, t4\n or t2, t2, t3\n"
      "vmv.x.s t3, v19\n xor t3, t3, t4\n or t2, t2, t3\n"
      "mv %[result], t2\n"
      : [result] "=&r"(result)
      :
      : "t0", "t1", "t2", "t3", "t4", "memory");

  const int failed = result != 0;
  printf("reduction min/max stream probe: result=%lx (%s)\n", result,
         failed ? "FAILED" : "PASSED");
  return failed;
}
