// SPDX-License-Identifier: Apache-2.0
// Unmasked NaN/finite streams exercise background context merges and VID reuse.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
#define S_(x) #x
#define S(x) S_(x)
#define RUN(W,OP,FINITE) \
static int run##W##OP(uint64_t one,uint64_t two,uint64_t nan,uint64_t canonical) { \
 uint64_t a,b,c,d,flags; \
 asm volatile( \
  "vsetvli t0, zero, e" S(W) ", m1, tu, mu\n" \
  "vmv.v.x v2, %[nan]\n" \
  "vmv.v.x v6, %[two]\n vmv.v.x v8, %[one]\n vmv.v.x v10, %[nan]\n" \
  "csrwi fflags, 0\n" \
  "vfred" S(OP) ".vs v12, v10, v2\n" \
  "vfred" S(OP) ".vs v14, v10, v6\n" \
  "vfred" S(OP) ".vs v16, v8, v6\n" \
  "vfred" S(OP) ".vs v18, v10, v2\n" \
  "vmv.x.s %[a], v12\n vmv.x.s %[b], v14\n" \
  "vmv.x.s %[c], v16\n vmv.x.s %[d], v18\n csrr %[flags], fflags\n" \
  : [a] "=&r"(a),[b] "=&r"(b),[c] "=&r"(c),[d] "=&r"(d),[flags] "=&r"(flags) \
  : [one] "r"(one),[two] "r"(two),[nan] "r"(nan) : "t0","memory"); \
 uint64_t mask=UINT64_MAX>>(64-W);a&=mask;b&=mask;c&=mask;d&=mask; \
 if(a!=canonical || b!=two || c!=FINITE || d!=canonical || flags) { \
  printf("minmax NaN stream FAIL e%u " S(OP) " a=%lx b=%lx c=%lx d=%lx flags=%lx\n",W,a,b,c,d,flags);return 1; \
 } return 0; \
}
RUN(16,min,one) RUN(16,max,two) RUN(32,min,one) RUN(32,max,two) RUN(64,min,one) RUN(64,max,two)
int main(void) {
 for(unsigned i=0;i<8;i++) {
  if(run16min(0x3c00,0x4000,0x7e55+i,0x7e00) || run16max(0x3c00,0x4000,0x7e55+i,0x7e00) ||
     run32min(0x3f800000,0x40000000,0x7fc12345+i,0x7fc00000) || run32max(0x3f800000,0x40000000,0x7fc12345+i,0x7fc00000) ||
     run64min(0x3ff0000000000000ULL,0x4000000000000000ULL,0x7ff8123456789abcULL+i,0x7ff8000000000000ULL) ||
     run64max(0x3ff0000000000000ULL,0x4000000000000000ULL,0x7ff8123456789abcULL+i,0x7ff8000000000000ULL)) return 1;
 }
 printf("minmax NaN stream PASS: 48 groups, 192 reductions\n");return 0;
}
