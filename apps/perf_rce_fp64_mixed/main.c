// SPDX-License-Identifier: Apache-2.0
// Same ELF for original tail, dedicated tail, and dedicated tail + mixed issue.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
#define PAIR(R,A) "vfredusum.vs " R ", v4, v2\nvfadd.vv " A ", v14, v16\n"
int main(void) {
  uint64_t start,end,a,b,c,d,add;
  asm volatile(
    "li t0, 16\nvsetvli t0, t0, e64, m1, tu, mu\n"
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
    : : "t0", "memory");
  if(a!=0x4033000000000000ULL || b!=0x4033000000000000ULL || c!=0x4033000000000000ULL || d!=0x4033000000000000ULL || add!=0x4022000000000000ULL) {
    printf("FAIL RCE FP64 mixed probe a=%lu b=%lu c=%lu d=%lu add=%lu\n",a,b,c,d,add);
    return 1;
  }
  printf("RCE FP64 mixed probe PASS: pairs=32 vl=16 sew=64 cycles=%lu\n",end-start);
  return 0;
}
