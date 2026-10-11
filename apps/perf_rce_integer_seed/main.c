// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
int main(void) {
  uint64_t begin,end,result;
  asm volatile(
    "li t0,32\nvsetvli zero,t0,e32,m1,tu,mu\n"
    "vmv.v.i v4,1\nvmv.v.i v8,3\ncsrr zero,vl\n"
    "rdcycle %[begin]\n.rept 32\nvredsum.vs v8,v4,v8\n.endr\n"
    "vmv.x.s %[r],v8\nrdcycle %[end]\n"
    : [begin] "=&r"(begin),[end] "=&r"(end),[r] "=&r"(result) :: "t0","memory");
  if(result!=1027) {printf("FAIL integer seed chain result=%lu expected=1027\n",result);return 1;}
  printf("RCE integer seed PASS: instructions=32 vl=32 sew=32 cycles=%lu\n",end-begin);
  return 0;
}
