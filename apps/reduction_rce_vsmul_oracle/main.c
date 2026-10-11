// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include <string.h>
#include "printf.h"
#include "runtime.h"
struct test_case {
  unsigned width, mode, sat;
  uint8_t a[128] __attribute__((aligned(128)));
  uint8_t b[128], mask[16], expected[128];
};
#include "cases.h"
static uint8_t result[128] __attribute__((aligned(128)));

#define RUN(W) asm volatile( \
  "vsetvli t0,zero,e" #W ",m1,tu,mu\n" \
  "vle" #W ".v v4,(%[a])\nvle" #W ".v v6,(%[b])\n" \
  "vle" #W ".v v8,(%[out])\nvlm.v v0,(%[mask])\n" \
  "csrw vxrm,%[mode]\ncsrwi vxsat,0\n" \
  "vsmul.vv v8,v4,v6,v0.t\ncsrr %[sat],vxsat\n" \
  "vse" #W ".v v8,(%[out])\ncsrr zero,vstart\n" \
  : [sat] "=&r"(sat) \
  : [a] "r"(c->a),[b] "r"(c->b),[mask] "r"(c->mask), \
    [mode] "r"((uint64_t)c->mode),[out] "r"(result) : "t0","memory")

int main(void) {
  for (unsigned n=0;n<sizeof(cases)/sizeof(cases[0]);n++) {
    const struct test_case *c=&cases[n]; uint64_t sat;
    for(unsigned i=0;i<128;i++) result[i]=0x5a;
    switch(c->width) {
      case 8: RUN(8);break;
      case 16: RUN(16);break;
      case 32: RUN(32);break;
      default: RUN(64);break;
    }
    if(sat!=c->sat) {
      printf("FAIL VSMUL case=%u width=%u mode=%u sat=%lu expected=%u\n",n,c->width,c->mode,sat,c->sat);return 1;
    }
    // Check every byte in 64-bit chunks to limit scalar simulator overhead.
    for(unsigned i=0;i<128;i+=8) {
      uint64_t actual,expected;
      memcpy(&actual,result+i,8);memcpy(&expected,c->expected+i,8);
      if(actual!=expected) {
        printf("FAIL VSMUL case=%u width=%u mode=%u byte=%u got=%lx expected=%lx\n",n,c->width,c->mode,i,actual,expected);return 1;
      }
    }
  }
  printf("VSMUL oracle PASS: 48 cases, SEW=8/16/32/64, four VXRM, active/mixed/empty masks\n");return 0;
}
