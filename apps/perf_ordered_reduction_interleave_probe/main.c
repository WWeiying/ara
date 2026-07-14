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
      "vmv.v.i v3, 0\n"
      "vmv.x.s t1, v3\n"
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
      "li t2, 0\n"
      "li t4, 32\n"
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

      // Negative fingerprint checks live outside the measured region.  A
      // different source register or seed register must execute normally and
      // must never reuse the preceding ordered-reduction result.
      "vmv.v.i v12, 2\n"
      "vmv.v.i v13, 1\n"
      "vfredosum.vs v14, v12, v2\n"
      "vfredosum.vs v15, v1,  v13\n"
      "vfredosum.vs v16, v1,  v2\n"
      "li t4, 64\n"
      "vmv.x.s t3, v14\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      "li t4, 33\n"
      "vmv.x.s t3, v15\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      "li t4, 32\n"
      "vmv.x.s t3, v16\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      // The register identities match v16, but an intervening vector write
      // changes the source value.  Central adjacency tagging must invalidate
      // fusion even though the filtered VMFPU/SLDU queues see the same names.
      "vmv.v.i v1, 3\n"
      "vfredosum.vs v17, v1, v2\n"
      "li t4, 96\n"
      "vmv.x.s t3, v17\n"
      "xor t3, t3, t4\n"
      "or t2, t2, t3\n"
      // Exception replay check.  The scalar CSR write is deliberately not a
      // vector instruction, so the second reduction remains an exact alias.
      // Wait long enough for the leader's NV pulse, clear fflags, then require
      // the alias retirement to raise the memoized NV contribution again.
      "li t5, 0x7f800001\n"
      "vmv.v.x v18, t5\n"
      "csrw fflags, zero\n"
      "vfredosum.vs v19, v18, v2\n"
      ".rept 256\n"
      "nop\n"
      ".endr\n"
      "csrw fflags, zero\n"
      "vfredosum.vs v20, v18, v2\n"
      "vmv.x.s t1, v20\n"
      "csrr t5, fflags\n"
      "andi t5, t5, 0x10\n"
      "xori t5, t5, 0x10\n"
      "or t2, t2, t5\n"
      "mv %[result], t2\n"
      : [result] "=&r"(result)
      :
      : "t0", "t1", "t2", "t3", "t4", "t5", "memory");

  const int failed = result != 0;
  printf("ordered reduction interleave probe: result=%lx (%s)\n", result,
         failed ? "FAILED" : "PASSED");
  return failed;
}
