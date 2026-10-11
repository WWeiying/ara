// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint32_t source[32] __attribute__((aligned(128)));
static uint32_t index_data[32] __attribute__((aligned(128)));
static uint32_t slide_out[32] __attribute__((aligned(128)));
static uint32_t load_out[32] __attribute__((aligned(128)));
int main(void) {
  for(unsigned i=0;i<32;i++) {source[i]=i+1; index_data[i]=4*(31-i);}
  uint64_t sum,maximum,xor_value;
  asm volatile(
    "li t0, 32\nvsetvli t0, t0, e32, m1, tu, mu\n"
    "vmv.v.i v4, 1\nvmv.v.i v2, 3\n"
    // Poison destination and neighboring source register independently:
    // VLMAX overflow must yield zero, never old vd or the next register.
    "vmv.v.i v10, -1\nvmv.v.i v7, -2\n"
    "vle32.v v6, (%[src])\nvle32.v v20, (%[idx])\n"
    "csrr zero, vstart\n"
    "vredsum.vs v8, v4, v2\n"
    "vslidedown.vi v10, v6, 1\n"
    "vredmaxu.vs v12, v6, v2\n"
    "vluxei32.v v18, (%[src]), v20\n"
    "vredxor.vs v22, v18, v2\n"
    "vse32.v v10, (%[slide])\nvse32.v v18, (%[load])\n"
    "vmv.x.s %[sum], v8\nvmv.x.s %[max], v12\nvmv.x.s %[xor], v22\n"
    "csrr zero, vstart\n"
    : [sum] "=&r"(sum), [max] "=&r"(maximum), [xor] "=&r"(xor_value)
    : [src] "r"(source), [idx] "r"(index_data), [slide] "r"(slide_out), [load] "r"(load_out)
    : "t0", "memory");
  if(sum!=35 || maximum!=32 || xor_value!=35) {
    printf("FAIL RCE shared scalar sum=%lu max=%lu xor=%lu\n",sum,maximum,xor_value); return 1;
  }
  for(unsigned i=0;i<32;i++)
    if(slide_out[i]!=(i==31?0:i+2) || load_out[i]!=32-i) {
      printf("FAIL RCE shared vector i=%u slide=%u load=%u\n",i,slide_out[i],load_out[i]);return 1;
    }
  printf("RCE shared PASS: Slide, indexed load, stores and load RAW\n");return 0;
}
