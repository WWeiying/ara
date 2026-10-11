// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
int main(void) {
  uint64_t a,b,c,d;
  asm volatile(
    "li t0, 32\nvsetvli t0, t0, e32, m1, tu, mu\n"
    "vmv.v.i v4, 1\nvmv.v.i v6, 2\nvmv.v.i v2, 3\n"
    "vmv.v.i v14, 5\nvmv.v.i v16, 7\nvmv.v.i v0, 0\nvmset.m v0\n"
    "vredsum.vs v8, v4, v2\n"
    "vredmaxu.vs v10, v6, v2\n"
    "vredxor.vs v12, v6, v2, v0.t\n"
    "vredand.vs v18, v14, v16, v0.t\n"
    "vmv.x.s %[a], v8\nvmv.x.s %[b], v10\n"
    "vmv.x.s %[c], v12\nvmv.x.s %[d], v18\n"
    : [a] "=&r"(a),[b] "=&r"(b),[c] "=&r"(c),[d] "=&r"(d) : : "t0","memory");
  if(a!=35 || b!=3 || c!=3 || d!=5) {
    printf("FAIL RCE heterogeneous opcode/mask a=%lu b=%lu c=%lu d=%lu\n",a,b,c,d);return 1;
  }
  asm volatile(
    "vsetivli t0, 8, e32, m1, tu, mu\nvredsum.vs v8, v4, v2\n"
    "vsetivli t0, 5, e32, m1, tu, mu\nvredor.vs v10, v6, v2\n"
    "vsetivli t0, 1, e32, m1, tu, mu\nvredmin.vs v12, v14, v16\n"
    "vsetivli t0, 31, e32, m1, tu, mu\nvredsum.vs v18, v4, v2\n"
    "vmv.x.s %[a], v8\nvmv.x.s %[b], v10\n"
    "vmv.x.s %[c], v12\nvmv.x.s %[d], v18\n"
    : [a] "=&r"(a),[b] "=&r"(b),[c] "=&r"(c),[d] "=&r"(d) : : "t0","memory");
  if(a!=11 || b!=3 || c!=5 || d!=34) {
    printf("FAIL RCE heterogeneous VL a=%lu b=%lu c=%lu d=%lu\n",a,b,c,d);return 1;
  }
  printf("RCE heterogeneous PASS: opcode, masked/unmasked, VL=1/5/8/31/32\n");return 0;
}
