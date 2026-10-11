// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint8_t mask_bytes[128] __attribute__((aligned(128)))={0,0,0,0,255,255,255,255};
static uint8_t output[64] __attribute__((aligned(128)));
int main(void) {
  uint64_t sat,sum;
  asm volatile(
    "li t0, 64\nvsetvli t0, t0, e8, m1, tu, mu\n"
    "vmv.v.i v4, 1\nvmv.v.i v2, 3\nvmv.v.i v14, -1\nvmv.v.i v12, 0\n"
    "vlm.v v0, (%[mask])\ncsrwi vxsat, 0\n"
    "vredsum.vs v8, v4, v2\n"
    "vsaddu.vv v12, v14, v4, v0.t\n"
    "vadd.vv v16, v4, v4\n"
    "csrr %[sat], vxsat\nvmv.x.s %[sum], v8\n"
    "vse8.v v12, (%[out])\ncsrr zero, vstart\n"
    : [sat] "=&r"(sat),[sum] "=&r"(sum)
    : [mask] "r"(mask_bytes),[out] "r"(output) : "t0","memory");
  if(sat!=1 || sum!=67) {
    printf("FAIL RCE masked saturation sat=%lu sum=%lu\n",sat,sum);return 1;
  }
  for(unsigned i=0;i<64;i++) if(output[i]!=(i<32?0:255)) {
    printf("FAIL RCE masked saturation vector i=%u value=%u\n",i,output[i]);return 1;
  }
  printf("RCE masked saturation PASS: flags belong to buffered result\n");return 0;
}
