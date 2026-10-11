// SPDX-License-Identifier: Apache-2.0
// Same ELF for original tail, dedicated tail, and dedicated tail + mixed issue.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
#define PAIR(R,A) "vfredusum.vs " R ", v4, v2, v0.t\nvfadd.vv " A ", v14, v16\n"
static int probe(uint64_t vl, uint64_t mask) {
  uint64_t start,end,a,b,c,d,add;
  asm volatile(
    "vsetvli t0, %[vl], e64, m1, tu, mu\n"
    "vmv.s.x v0, %[mask]\n"
    "li t0, 0x3ff0000000000000\nvmv.v.x v4, t0\nli t0, 0x4008000000000000\nvmv.v.x v2, t0\n"
    "li t0, 0x4010000000000000\nvmv.v.x v14, t0\nli t0, 0x4014000000000000\nvmv.v.x v16, t0\n"
    "csrr zero, vstart\ncsrr %[start], cycle\n"
    ".rept 8\n"
    PAIR("v8","v12") PAIR("v10","v18")
    PAIR("v20","v24") PAIR("v22","v26")
    ".endr\n"
    "csrr zero, vstart\ncsrr %[end], cycle\n"
    "vmv.x.s %[a], v8\nvmv.x.s %[b], v10\n"
    "vmv.x.s %[c], v20\nvmv.x.s %[d], v22\nvmv.x.s %[add], v26\n"
    : [start] "=&r"(start), [end] "=&r"(end), [a] "=&r"(a),
      [b] "=&r"(b), [c] "=&r"(c), [d] "=&r"(d), [add] "=&r"(add)
    : [vl] "r"(vl), [mask] "r"(mask) : "t0", "memory");
  unsigned active = 0;
  for (unsigned i=0; i<vl; i++) active += (mask >> i) & 1;
  union { double f; uint64_t u; } expected = {.f = (double)(3 + active)};
  if(a!=expected.u || b!=expected.u || c!=expected.u || d!=expected.u || add!=0x4022000000000000ULL) {
    printf("FAIL RCE FP64 mixed probe a=%lu b=%lu c=%lu d=%lu add=%lu\n",a,b,c,d,add);
    return 1;
  }
  printf("RCE FP64 sparse PASS: pairs=32 vl=%lu mask=%lu sew=64 cycles=%lu\n",vl,mask,end-start);
  return 0;
}

int main(void) {
  asm volatile("vsetvli t0,zero,e8,m8,tu,mu\nvmv.v.i v0,0\nvmv.v.i v8,0\nvmv.v.i v16,0\nvmv.v.i v24,0\n" ::: "t0", "memory");
  const uint64_t cases[][2] = {{1,1},{2,3},{3,7},{4,15},{4,9},{4,10},{4,8},{4,2},{4,0},{16,0x9999},{16,0xffff}};
  for (unsigned i=0; i<sizeof(cases)/sizeof(cases[0]); i++)
    if (probe(cases[i][0],cases[i][1])) return 1;
  return 0;
}
