// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
int main(void) {
  uint64_t sum, count, sat, value;
  asm volatile(
    "li t0, 32\nvsetvli t0, t0, e32, m1, tu, mu\n"
    "vmv.v.i v4, 1\nvmv.v.i v2, 3\nvmv.v.i v14, 4\n"
    "vredsum.vs v8, v4, v2\n"
    "vmseq.vv v0, v14, v14\n"
    "vcpop.m %[count], v0\nvmv.x.s %[sum], v8\n"
    : [count] "=&r"(count), [sum] "=&r"(sum) : : "t0", "memory");
  if(sum != 35 || count != 32) {
    printf("FAIL RCE mask ownership sum=%lu count=%lu\n",sum,count); return 1;
  }
  asm volatile(
    "li t0, 128\nvsetvli t0, t0, e8, m1, tu, mu\n"
    "vmv.v.i v4, 1\nvmv.v.i v2, 3\nvmv.v.i v14, -1\n"
    "csrwi vxsat, 0\n"
    "vredsum.vs v8, v4, v2\n"
    "vsaddu.vv v12, v14, v4\n"
    "vadd.vv v16, v4, v4\n"
    "csrr %[sat], vxsat\nvmv.x.s %[value], v12\nvmv.x.s %[sum], v8\n"
    : [sat] "=&r"(sat), [value] "=&r"(value), [sum] "=&r"(sum)
    : : "t0", "memory");
  if(sat != 1 || (value&255) != 255 || (sum&255) != 131) {
    printf("FAIL RCE saturation sat=%lu value=%lx sum=%lx\n",sat,value,sum); return 1;
  }
  printf("RCE ownership PASS: mask result and saturation flag\n");
  return 0;
}
