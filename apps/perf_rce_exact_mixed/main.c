// SPDX-License-Identifier: Apache-2.0
// Same ELF for original tail, dedicated tail, and dedicated tail + mixed issue.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
#define PAIR(R,A) "vfredusum.vs " R ", v4, v2\nvfadd.vv " A ", v14, v16\n"
int main(void) {
  uint64_t start,end,a,b,c,d,add;
  asm volatile(
    "li t0, 32\nvsetvli t0, t0, e32, m1, tu, mu\n"
    "li t0, 0x3f800000\nvmv.v.x v4, t0\nli t0, 0x40400000\nvmv.v.x v2, t0\n"
    "li t0, 0x40800000\nvmv.v.x v14, t0\nli t0, 0x40a00000\nvmv.v.x v16, t0\n"
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
    : : "t0", "memory");
  if(a!=0x420c0000 || b!=0x420c0000 || c!=0x420c0000 || d!=0x420c0000 || add!=0x41100000) {
    printf("FAIL RCE exact mixed probe a=%lu b=%lu c=%lu d=%lu add=%lu\n",a,b,c,d,add);
    return 1;
  }
  printf("RCE exact mixed probe PASS: pairs=32 vl=32 sew=32 cycles=%lu\n",end-start);
  return 0;
}
