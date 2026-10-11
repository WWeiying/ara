// SPDX-License-Identifier: Apache-2.0
// Check independent same-MFPU work, a true reduction-result RAW, and a
// comparison routed through MASKU. Check all ordinary destination elements.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint32_t add_out[32] __attribute__((aligned(128)));
static uint32_t mul_out[32] __attribute__((aligned(128)));
static uint32_t raw_out[32] __attribute__((aligned(128)));
static uint8_t cmp_out[16] __attribute__((aligned(128)));
int main(void) {
  uint64_t rmin, rmax, rmin2, rafter, flags;
  asm volatile(
    "li t0, 32\nvsetvli t0, t0, e32, m1, tu, mu\n"
    "li t0, 0x40000000\nvmv.v.x v4, t0\n" // 2
    "li t0, 0x40400000\nvmv.v.x v2, t0\n" // seed 3
    "li t0, 0x3f800000\nvmv.v.x v14, t0\n" // 1
    "vmv.v.i v0, 0\nvmv.v.i v8, 0\nvmv.v.i v10, 0\n"
    "vmv.v.i v18, 0\nvmv.v.i v24, 0\nvmv.v.i v20, 0\n"
    "csrwi fflags, 0\n"
    "vfredusum.vs v8, v4, v2\n"
    "vfadd.vv v12, v14, v4\n"
    "vfredmax.vs v10, v4, v2\n"
    "vfmul.vv v16, v14, v4\n"
    "vfredusum.vs v18, v4, v2\n"
    "vmflt.vv v20, v14, v4\n"
    "vfadd.vv v22, v8, v14\n" // Must read committed v8[0] = 67
    "vfredmax.vs v24, v12, v14\n" // Ordinary-result RAW
    "vmv.x.s %[a], v8\nvmv.x.s %[b], v10\n"
    "vmv.x.s %[c], v18\nvmv.x.s %[d], v24\n"
    "vse32.v v12, (%[add])\nvse32.v v16, (%[mul])\n"
    "vse32.v v22, (%[raw])\nvsm.v v20, (%[cmp])\n"
    "csrr %[flags], fflags\ncsrr zero, vstart\n"
    : [a] "=&r"(rmin), [b] "=&r"(rmax), [c] "=&r"(rmin2),
      [d] "=&r"(rafter), [flags] "=&r"(flags)
    : [add] "r"(add_out), [mul] "r"(mul_out), [raw] "r"(raw_out),
      [cmp] "r"(cmp_out) : "t0", "memory");
  if(rmin!=0x42860000 || rmax!=0x40400000 || rmin2!=0x42860000 ||
     rafter!=0x40400000 || flags!=0) {
    printf("FAIL RCE exact FP scalar min=%lx max=%lx min2=%lx after=%lx flags=%lx\n",
      rmin,rmax,rmin2,rafter,flags);return 1;
  }
  for(unsigned i=0;i<32;i++) {
    if(add_out[i]!=0x40400000 || mul_out[i]!=0x40000000 ||
       raw_out[i]!=(i==0?0x42880000:0x3f800000)) {
      printf("FAIL RCE exact FP vector i=%u add=%x mul=%x raw=%x\n",
        i,add_out[i],mul_out[i],raw_out[i]);return 1;
    }
  }
  for(unsigned i=0;i<4;i++) if(cmp_out[i]!=255) {
    printf("FAIL RCE exact FP compare byte=%u value=%u\n",i,cmp_out[i]);return 1;
  }
  printf("RCE exact FP mixed PASS: add/mul/compare, forward and reverse RAW\n");
  return 0;
}
