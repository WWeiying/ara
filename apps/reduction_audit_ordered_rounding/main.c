// SPDX-License-Identifier: Apache-2.0
// Ordered rounding and inactive-source semantics, independent of tree sums.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint64_t source[4] __attribute__((aligned(64)));
static uint8_t mask[8] __attribute__((aligned(8)));
#define STR_(x) #x
#define STR(x) STR_(x)
#define RUN(W) \
static void run##W(unsigned vl, unsigned rm, uint64_t seed, uint64_t *result, uint64_t *flags) { \
  uint64_t r, f; \
  asm volatile( \
    "li t0, 2\n vsetvli t0, t0, e8, m1, tu, mu\n" \
    "vle8.v v0, (%[mask])\n" \
    "vsetvli t0, %[vl], e" STR(W) ", m1, tu, mu\n" \
    "vle" STR(W) ".v v8, (%[src])\n" \
    "vmv.v.x v2, %[seed]\n vmv.v.i v4, 0\n" \
    "csrw frm, %[rm]\n csrwi fflags, 0\n" \
    "vfredosum.vs v4, v8, v2, v0.t\n" \
    "vmv.x.s %[result], v4\n csrr %[flags], fflags\n csrwi frm, 0\n" \
    : [result] "=&r"(r), [flags] "=&r"(f) \
    : [vl] "r"((uint64_t)vl), [rm] "r"((uint64_t)rm), [seed] "r"(seed), \
      [src] "r"(source), [mask] "r"(mask) : "t0", "memory"); \
  *result=r; *flags=f; \
}
RUN(16)
RUN(32)
RUN(64)
struct format { unsigned width; uint64_t one,two,large,snan,qnan,canonical,sign; void (*run)(unsigned,unsigned,uint64_t,uint64_t*,uint64_t*); };
static const struct format formats[]={
 {16,0x3c00,0x4000,0x6800,0x7c01,0x7e55,0x7e00,0x8000,run16},
 {32,0x3f800000,0x40000000,0x4b800000,0x7f800001,0x7fc12345,0x7fc00000,0x80000000,run32},
 {64,0x3ff0000000000000ULL,0x4000000000000000ULL,0x4340000000000000ULL,
  0x7ff0000000000001ULL,0x7ff8123456789abcULL,0x7ff8000000000000ULL,0x8000000000000000ULL,run64}
};
static void set_source(unsigned width, const uint64_t *values) {
  uint8_t *bytes=(uint8_t*)source;
  for(unsigned i=0;i<4;++i)
    for(unsigned b=0;b<width/8;++b) bytes[i*(width/8)+b]=(uint8_t)(values[i]>>(8*b));
}
int main(void) {
  unsigned cases=0;
  for(unsigned k=0;k<3;++k) {
    const struct format *f=&formats[k];
    for(unsigned test=0;test<10;++test) {
      uint64_t values[4]={0,0,0,0},seed=0,want=0,want_flags=0;
      unsigned vl=3,rm=0;
      mask[0]=0xff;mask[1]=0;
      if(test<5) {
        // seed + [2^p, 1, -2^p]: the middle add is exactly halfway
        // between representable numbers. A reassociated tree could return 1.
        values[0]=f->large;values[1]=f->one;values[2]=f->large|f->sign;
        rm=test;want=(rm==3 || rm==4)?f->two:(rm==2?f->sign:0);want_flags=1;
      } else if(test==5) {
        seed=f->qnan;mask[0]=0;want=f->qnan;
      } else if(test==6) {
        values[0]=f->one;values[1]=f->snan;values[2]=f->one;
        seed=f->two;mask[0]=5;want=f->two+(1ULL<<(f->width==16?10:f->width==32?23:52)); // 4.0
      } else if(test==7) {
        values[0]=f->snan;seed=f->two;vl=1;want=f->canonical;want_flags=16;
      } else if(test==8) {
        seed=f->sign;mask[0]=0;want=f->sign;
      } else {
        // Exact cancellation under downward rounding produces negative zero.
        values[0]=f->one;values[1]=f->one|f->sign;vl=2;rm=2;want=f->sign;
      }
      set_source(f->width,values);
      uint64_t got,flags;f->run(vl,rm,seed,&got,&flags);
      if(f->width<64) got&=(1ULL<<f->width)-1;
      if(got!=want || flags!=want_flags) {
        printf("ordered rounding FAIL width=%u case=%u result=%lx/%lx flags=%lx/%lx\n",f->width,test,got,want,flags,want_flags);
        return 1;
      }
      ++cases;
    }
  }
  printf("ordered rounding PASS: %u cases\n",cases);
  return 0;
}
