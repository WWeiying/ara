// SPDX-License-Identifier: Apache-2.0
// Exact 2 and inexact +/-1/3, sqrt(2), under all five architectural FRM modes.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint64_t output[4] __attribute__((aligned(128)));
static const struct { uint64_t a,b,lower,upper; unsigned sqrt,nx,negative; } cases[] = {
  {0x3ff0000000000000ULL,0x3fe0000000000000ULL,0x4000000000000000ULL,0x4000000000000000ULL,0,0,0},
  {0x3ff0000000000000ULL,0x4008000000000000ULL,0x3fd5555555555555ULL,0x3fd5555555555556ULL,0,1,0},
  {0xbff0000000000000ULL,0x4008000000000000ULL,0xbfd5555555555555ULL,0xbfd5555555555556ULL,0,1,1},
  {0x4000000000000000ULL,0,0x3ff6a09e667f3bccULL,0x3ff6a09e667f3bcdULL,1,1,0},
  {0x4010000000000000ULL,0,0x4000000000000000ULL,0x4000000000000000ULL,1,0,0},
};
int main(void) {
  for(unsigned rm=0;rm<5;rm++) for(unsigned c=0;c<5;c++) {
    uint64_t flags;
    asm volatile("vsetivli zero,4,e64,m1,tu,mu\nvmv.v.x v4,%0\nvmv.v.x v6,%1\ncsrw frm,%2\ncsrwi fflags,0\n"
      :: "r"(cases[c].a),"r"(cases[c].b),"r"((uint64_t)rm) : "memory");
    if(cases[c].sqrt) asm volatile("vfsqrt.v v8,v4" ::: "memory");
    else asm volatile("vfdiv.vv v8,v4,v6" ::: "memory");
    asm volatile("vse64.v v8,(%1)\ncsrr %0,fflags" : "=&r"(flags) : "r"(output) : "memory");
    unsigned upper=(rm==2 && cases[c].negative) || (rm==3 && !cases[c].negative) ||
                   ((rm==0 || rm==4) && c==3);
    uint64_t expected=upper?cases[c].upper:cases[c].lower;
    for(unsigned i=0;i<4;i++) if(output[i]!=expected || flags!=cases[c].nx) {
      printf("FAIL DIV rounding case=%u rm=%u lane=%u got=%lx expected=%lx flags=%lx expected_flags=%u\n",c,rm,i,output[i],expected,flags,cases[c].nx);return 1;
    }
  }
  asm volatile("csrwi frm,0" ::: "memory");
  printf("RCE DIV rounding PASS: 25 exact/inexact FP64 value and flag cases\n");
  return 0;
}
