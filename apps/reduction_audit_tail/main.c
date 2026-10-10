// SPDX-License-Identifier: Apache-2.0
// Check every destination byte, including tails and VL=0, using TU/MU.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
#define BYTES (VLEN / 8)
#ifndef AUDIT_FIRST_TEST
#define AUDIT_FIRST_TEST 0
#endif
#ifndef AUDIT_LAST_TEST
#define AUDIT_LAST_TEST UINT32_MAX
#endif
#ifndef AUDIT_FIRST_LENGTH
#define AUDIT_FIRST_LENGTH 0
#endif
static uint8_t src[BYTES] __attribute__((aligned(128)));
static uint8_t seed[BYTES] __attribute__((aligned(128)));
static uint8_t before[BYTES] __attribute__((aligned(128)));
static union { uint64_t words[BYTES/8]; uint8_t bytes[BYTES]; } output __attribute__((aligned(128)));
static uint8_t mask[BYTES] __attribute__((aligned(128)));
#define STR_(x) #x
#define STR(x) STR_(x)
#define DEFINE_RUN(NAME, OP, SW, DW) \
static void NAME(unsigned vl, unsigned unmasked, uint64_t *flags) { \
  asm volatile( \
    "li t0, " STR(VLEN / DW) "\n" \
    "vsetvli t0, t0, e" STR(DW) ", m1, tu, mu\n" \
    "vmv.v.i v10, -1\n" \
    "vse" STR(DW) ".v v10, (%[after])\n" \
    "vle" STR(DW) ".v v4, (%[before])\n" \
    "vle" STR(DW) ".v v2, (%[seed])\n" \
    "li t0, " STR(VLEN / SW) "\n" \
    "vsetvli t0, t0, e" STR(SW) ", m1, tu, mu\n" \
    "vle" STR(SW) ".v v8, (%[src])\n" \
    "li t0, " STR(BYTES) "\n" \
    "vsetvli t0, t0, e8, m1, tu, mu\n" \
    "vle8.v v0, (%[mask])\n" \
    "vsetvli t0, %[vl], e" STR(SW) ", m1, tu, mu\n" \
    "csrwi fflags, 0\n" \
    : : [before] "r"(before), [seed] "r"(seed), [src] "r"(src), \
        [mask] "r"(mask), [after] "r"(output.bytes), [vl] "r"((uint64_t)vl) : "t0", "memory"); \
  if (unmasked) asm volatile(STR(OP) " v4, v8, v2" ::: "memory"); \
  else asm volatile(STR(OP) " v4, v8, v2, v0.t" ::: "memory"); \
  uint64_t f; \
  asm volatile( \
    "csrr %[flags], fflags\n" \
    "li t0, " STR(VLEN / DW) "\n" \
    "vsetvli t0, t0, e" STR(DW) ", m1, tu, mu\n" \
    "vse" STR(DW) ".v v4, (%[after])\n" \
    "csrr zero, vstart\n" \
    : [flags] "=&r"(f) : [after] "r"(output.bytes) : "t0", "memory"); \
  *flags=f; \
}
DEFINE_RUN(vredsum_8, vredsum.vs, 8, 8)
DEFINE_RUN(vredand_8, vredand.vs, 8, 8)
DEFINE_RUN(vredor_8, vredor.vs, 8, 8)
DEFINE_RUN(vredxor_8, vredxor.vs, 8, 8)
DEFINE_RUN(vredmin_8, vredmin.vs, 8, 8)
DEFINE_RUN(vredminu_8, vredminu.vs, 8, 8)
DEFINE_RUN(vredmax_8, vredmax.vs, 8, 8)
DEFINE_RUN(vredmaxu_8, vredmaxu.vs, 8, 8)
DEFINE_RUN(vwredsum_8, vwredsum.vs, 8, 16)
DEFINE_RUN(vwredsumu_8, vwredsumu.vs, 8, 16)
DEFINE_RUN(vredsum_16, vredsum.vs, 16, 16)
DEFINE_RUN(vredand_16, vredand.vs, 16, 16)
DEFINE_RUN(vredor_16, vredor.vs, 16, 16)
DEFINE_RUN(vredxor_16, vredxor.vs, 16, 16)
DEFINE_RUN(vredmin_16, vredmin.vs, 16, 16)
DEFINE_RUN(vredminu_16, vredminu.vs, 16, 16)
DEFINE_RUN(vredmax_16, vredmax.vs, 16, 16)
DEFINE_RUN(vredmaxu_16, vredmaxu.vs, 16, 16)
DEFINE_RUN(vwredsum_16, vwredsum.vs, 16, 32)
DEFINE_RUN(vwredsumu_16, vwredsumu.vs, 16, 32)
DEFINE_RUN(vredsum_32, vredsum.vs, 32, 32)
DEFINE_RUN(vredand_32, vredand.vs, 32, 32)
DEFINE_RUN(vredor_32, vredor.vs, 32, 32)
DEFINE_RUN(vredxor_32, vredxor.vs, 32, 32)
DEFINE_RUN(vredmin_32, vredmin.vs, 32, 32)
DEFINE_RUN(vredminu_32, vredminu.vs, 32, 32)
DEFINE_RUN(vredmax_32, vredmax.vs, 32, 32)
DEFINE_RUN(vredmaxu_32, vredmaxu.vs, 32, 32)
DEFINE_RUN(vwredsum_32, vwredsum.vs, 32, 64)
DEFINE_RUN(vwredsumu_32, vwredsumu.vs, 32, 64)
DEFINE_RUN(vredsum_64, vredsum.vs, 64, 64)
DEFINE_RUN(vredand_64, vredand.vs, 64, 64)
DEFINE_RUN(vredor_64, vredor.vs, 64, 64)
DEFINE_RUN(vredxor_64, vredxor.vs, 64, 64)
DEFINE_RUN(vredmin_64, vredmin.vs, 64, 64)
DEFINE_RUN(vredminu_64, vredminu.vs, 64, 64)
DEFINE_RUN(vredmax_64, vredmax.vs, 64, 64)
DEFINE_RUN(vredmaxu_64, vredmaxu.vs, 64, 64)
DEFINE_RUN(vfredosum_16, vfredosum.vs, 16, 16)
DEFINE_RUN(vfredusum_16, vfredusum.vs, 16, 16)
DEFINE_RUN(vfredmin_16, vfredmin.vs, 16, 16)
DEFINE_RUN(vfredmax_16, vfredmax.vs, 16, 16)
DEFINE_RUN(vfwredosum_16, vfwredosum.vs, 16, 32)
DEFINE_RUN(vfwredusum_16, vfwredusum.vs, 16, 32)
DEFINE_RUN(vfredosum_32, vfredosum.vs, 32, 32)
DEFINE_RUN(vfredusum_32, vfredusum.vs, 32, 32)
DEFINE_RUN(vfredmin_32, vfredmin.vs, 32, 32)
DEFINE_RUN(vfredmax_32, vfredmax.vs, 32, 32)
DEFINE_RUN(vfwredosum_32, vfwredosum.vs, 32, 64)
DEFINE_RUN(vfwredusum_32, vfwredusum.vs, 32, 64)
DEFINE_RUN(vfredosum_64, vfredosum.vs, 64, 64)
DEFINE_RUN(vfredusum_64, vfredusum.vs, 64, 64)
DEFINE_RUN(vfredmin_64, vfredmin.vs, 64, 64)
DEFINE_RUN(vfredmax_64, vfredmax.vs, 64, 64)

struct test { const char *name; unsigned sw,dw,fp,kind; void (*run)(unsigned,unsigned,uint64_t *); };
static const struct test tests[] = {
  {"vredsum_8",8,8,0,0,vredsum_8},
  {"vredand_8",8,8,0,1,vredand_8},
  {"vredor_8",8,8,0,2,vredor_8},
  {"vredxor_8",8,8,0,3,vredxor_8},
  {"vredmin_8",8,8,0,4,vredmin_8},
  {"vredminu_8",8,8,0,4,vredminu_8},
  {"vredmax_8",8,8,0,5,vredmax_8},
  {"vredmaxu_8",8,8,0,5,vredmaxu_8},
  {"vwredsum_8",8,16,0,0,vwredsum_8},
  {"vwredsumu_8",8,16,0,0,vwredsumu_8},
  {"vredsum_16",16,16,0,0,vredsum_16},
  {"vredand_16",16,16,0,1,vredand_16},
  {"vredor_16",16,16,0,2,vredor_16},
  {"vredxor_16",16,16,0,3,vredxor_16},
  {"vredmin_16",16,16,0,4,vredmin_16},
  {"vredminu_16",16,16,0,4,vredminu_16},
  {"vredmax_16",16,16,0,5,vredmax_16},
  {"vredmaxu_16",16,16,0,5,vredmaxu_16},
  {"vwredsum_16",16,32,0,0,vwredsum_16},
  {"vwredsumu_16",16,32,0,0,vwredsumu_16},
  {"vredsum_32",32,32,0,0,vredsum_32},
  {"vredand_32",32,32,0,1,vredand_32},
  {"vredor_32",32,32,0,2,vredor_32},
  {"vredxor_32",32,32,0,3,vredxor_32},
  {"vredmin_32",32,32,0,4,vredmin_32},
  {"vredminu_32",32,32,0,4,vredminu_32},
  {"vredmax_32",32,32,0,5,vredmax_32},
  {"vredmaxu_32",32,32,0,5,vredmaxu_32},
  {"vwredsum_32",32,64,0,0,vwredsum_32},
  {"vwredsumu_32",32,64,0,0,vwredsumu_32},
  {"vredsum_64",64,64,0,0,vredsum_64},
  {"vredand_64",64,64,0,1,vredand_64},
  {"vredor_64",64,64,0,2,vredor_64},
  {"vredxor_64",64,64,0,3,vredxor_64},
  {"vredmin_64",64,64,0,4,vredmin_64},
  {"vredminu_64",64,64,0,4,vredminu_64},
  {"vredmax_64",64,64,0,5,vredmax_64},
  {"vredmaxu_64",64,64,0,5,vredmaxu_64},
  {"vfredosum_16",16,16,1,0,vfredosum_16},
  {"vfredusum_16",16,16,1,0,vfredusum_16},
  {"vfredmin_16",16,16,1,4,vfredmin_16},
  {"vfredmax_16",16,16,1,5,vfredmax_16},
  {"vfwredosum_16",16,32,1,0,vfwredosum_16},
  {"vfwredusum_16",16,32,1,0,vfwredusum_16},
  {"vfredosum_32",32,32,1,0,vfredosum_32},
  {"vfredusum_32",32,32,1,0,vfredusum_32},
  {"vfredmin_32",32,32,1,4,vfredmin_32},
  {"vfredmax_32",32,32,1,5,vfredmax_32},
  {"vfwredosum_32",32,64,1,0,vfwredosum_32},
  {"vfwredusum_32",32,64,1,0,vfwredusum_32},
  {"vfredosum_64",64,64,1,0,vfredosum_64},
  {"vfredusum_64",64,64,1,0,vfredusum_64},
  {"vfredmin_64",64,64,1,4,vfredmin_64},
  {"vfredmax_64",64,64,1,5,vfredmax_64},
};
// Exact IEEE encoding of the small positive integers used by this test.
static uint64_t fp_integer(unsigned n, unsigned width) {
  unsigned f=width==16?10:width==32?23:52;
  unsigned bias=width==16?15:width==32?127:1023;
  unsigned top=0;
  for(unsigned x=n;x>1;x>>=1) ++top;
  return ((uint64_t)(bias+top)<<f) | ((uint64_t)(n-(1u<<top))<<(f-top));
}
static void put(uint8_t *p, unsigned bytes, uint64_t value) {
  for(unsigned b=0;b<bytes;++b) p[b]=(uint8_t)(value>>(8*b));
}
int main(void) {
  // Boundary coverage, not the Cartesian product: all opcodes and widths use
  // VL=0, VL=1, all-inactive, alternating masks, odd tails, and unmasked input.
  const unsigned lengths[]={0,1,3,5,7,15};
  const unsigned modes[]  ={3,1,0,2,3,2};
  const uint64_t sentinel=0x123456789abcdef0ULL;
  unsigned cases=0;
  for(unsigned b=0;b<BYTES;b+=8) put(before+b,8,sentinel);
  for(unsigned t=AUDIT_FIRST_TEST;t<sizeof(tests)/sizeof(tests[0]) && t<AUDIT_LAST_TEST;++t) {
    const struct test *test=&tests[t];
    for(unsigned b=0;b<BYTES;b+=test->sw/8)
      put(src+b,test->sw/8,test->fp?fp_integer(1,test->sw):3);
    for(unsigned b=0;b<BYTES;b+=test->dw/8)
      put(seed+b,test->dw/8,test->fp?fp_integer(2,test->dw):7);
    for(unsigned l=AUDIT_FIRST_LENGTH;l<sizeof(lengths)/sizeof(lengths[0]);++l) {
      unsigned vl=lengths[l], mode=modes[l];
      unsigned active=mode==0?0:mode==2?vl/2:vl;
      for(unsigned b=0;b<BYTES;++b) mask[b]=mode==0?0:mode==2?0xaa:0xff;
      uint64_t flags;
      test->run(vl,mode==3,&flags);
      unsigned expected=test->fp?2:7;
      if(test->kind==0) expected+=active*(test->fp?1:3);
      else if(test->kind==1 && active) expected&=3;
      else if(test->kind==2 && active) expected|=3;
      else if(test->kind==3 && (active&1)) expected^=3;
      else if(test->kind==4 && active) expected=test->fp?1:3;
      uint64_t bits=test->fp?fp_integer(expected,test->dw):expected;
      uint64_t element_mask=test->dw==64?UINT64_MAX:((1ULL<<test->dw)-1);
      uint64_t first=vl?((sentinel&~element_mask)|(bits&element_mask)):sentinel;
      for(unsigned w=0;w<BYTES/8;++w) {
        uint64_t want=w?sentinel:first;
        if(output.words[w]!=want) {
          printf("tail FAIL op=%s vl=%u mode=%u word=%u got=%lx expected=%lx\n",
                 test->name,vl,mode,w,output.words[w],want);
          return 1;
        }
      }
      if(flags) { printf("tail FAIL op=%s flags=%lx\n",test->name,flags); return 1; }
      ++cases;
    }
  }
  printf("tail audit PASS: %u cases, each checks %u destination bytes\n",cases,BYTES);
  return 0;
}
