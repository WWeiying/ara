// SPDX-License-Identifier: Apache-2.0
// Interleave all currently integrated completion backends, exercise true
// integer and exact-FP seed dependencies, and check ordinary vector results.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint32_t fp_out[32] __attribute__((aligned(128)));
static uint32_t int_out[32] __attribute__((aligned(128)));
int main(void) {
  uint64_t isum, fsum, ixor, fmax, fchain, ichain, fmin, flags;
  asm volatile(
    "li t0, 32\nvsetvli t0, t0, e32, m1, tu, mu\n"
    "li t0, 0x3f800000\nvmv.v.x v4, t0\nvmv.v.x v2, t0\n"
    "vmv.v.i v6, 1\nvmv.v.i v3, 3\ncsrwi fflags, 0\n"
    "vredsum.vs v8, v6, v3\n"
    "vfredusum.vs v12, v4, v2\n"
    "vredxor.vs v14, v6, v3\n"
    "vfredmax.vs v16, v4, v2\n"
    "vfadd.vv v24, v4, v4\n"
    "vfredusum.vs v20, v4, v12\n"
    "vredsum.vs v18, v6, v8\n"
    "vfredmin.vs v22, v24, v20\n"
    "vadd.vv v26, v6, v6\n"
    "vmv.x.s %[isum], v8\nvmv.x.s %[fsum], v12\n"
    "vmv.x.s %[ixor], v14\nvmv.x.s %[fmax], v16\n"
    "vmv.x.s %[fchain], v20\nvmv.x.s %[ichain], v18\n"
    "vmv.x.s %[fmin], v22\n"
    "vse32.v v24, (%[fpout])\nvse32.v v26, (%[intout])\n"
    "csrr %[flags], fflags\ncsrr zero, vstart\n"
    : [isum] "=&r"(isum), [fsum] "=&r"(fsum), [ixor] "=&r"(ixor),
      [fmax] "=&r"(fmax), [fchain] "=&r"(fchain), [ichain] "=&r"(ichain),
      [fmin] "=&r"(fmin), [flags] "=&r"(flags)
    : [fpout] "r"(fp_out), [intout] "r"(int_out) : "t0", "memory");
  if(isum!=35 || fsum!=0x42040000 || ixor!=3 || fmax!=0x3f800000 ||
     fchain!=0x42820000 || ichain!=67 || fmin!=0x40000000 || flags!=0) {
    printf("FAIL RCE backends sum=%lx/%lx xor=%lx max=%lx chain=%lx/%lx min=%lx flags=%lx\n",
      isum,fsum,ixor,fmax,fchain,ichain,fmin,flags);return 1;
  }
  for(unsigned i=0;i<32;i++) if(fp_out[i]!=0x40000000 || int_out[i]!=2) {
    printf("FAIL RCE backend vector i=%u fp=%x int=%x\n",i,fp_out[i],int_out[i]);return 1;
  }
  printf("RCE backend mix PASS: integer/exact/minmax, seed RAW, full vectors\n");
  return 0;
}
