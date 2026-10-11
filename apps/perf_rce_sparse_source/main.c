// SPDX-License-Identifier: Apache-2.0
// Same ELF for original tail, dedicated tail, and dedicated tail + mixed issue.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
#define PAIR(R,A) "vredsum.vs " R ", v4, v2\nvadd.vv " A ", v14, v16\n"
static int probe(uint64_t vl) {
  uint64_t start,end,a,b,c,d,add;
  asm volatile(
    "vsetvli t0, %[vl], e32, m1, tu, mu\n"
    "vmv.v.i v4, 1\nvmv.v.i v2, 3\nvmv.v.i v14, 4\nvmv.v.i v16, 5\n"
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
    : [vl] "r"(vl) : "t0", "memory");
  if(a!=vl+3 || b!=vl+3 || c!=vl+3 || d!=vl+3 || add!=9) {
    printf("FAIL RCE mixed probe a=%lu b=%lu c=%lu d=%lu add=%lu\n",a,b,c,d,add);
    return 1;
  }
  printf("RCE sparse source PASS: pairs=32 vl=%lu sew=32 cycles=%lu\n",vl,end-start);
  return 0;
}

int main(void) {
  // Initialize all tail words before changing VL between measurement windows.
  asm volatile("vsetvli t0,zero,e8,m8,tu,mu\nvmv.v.i v0,0\nvmv.v.i v8,0\nvmv.v.i v16,0\nvmv.v.i v24,0\n" ::: "t0", "memory");
  const uint64_t lengths[] = {1, 2, 3, 4, 8, 32};
  for (unsigned i = 0; i < sizeof(lengths)/sizeof(lengths[0]); i++)
    if (probe(lengths[i])) return 1;
  return 0;
}
