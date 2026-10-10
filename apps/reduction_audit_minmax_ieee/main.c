// SPDX-License-Identifier: Apache-2.0
// Independent bit-pattern expectations for min/max, NaNs, masks and short VL.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static union { uint8_t bytes[128]; uint64_t words[16]; } source __attribute__((aligned(128)));
static uint8_t mask[8] __attribute__((aligned(8)));
#define STR_(x) #x
#define STR(x) STR_(x)
#define RUN(W, OP) \
static void run##W##OP(unsigned vl, uint64_t seed, unsigned initial_flags, uint64_t *r, uint64_t *f) { \
  uint64_t result, flags; \
  asm volatile( \
    "li t0, 8\n vsetvli t0, t0, e8, m1, tu, mu\n vle8.v v0, (%[mask])\n" \
    "vsetvli t0, zero, e" STR(W) ", m1, tu, mu\n" \
    "vle" STR(W) ".v v8, (%[source])\n" \
    "vmv.v.x v2, %[seed]\n vmv.v.i v4, 7\n" \
    "vsetvli t0, %[vl], e" STR(W) ", m1, tu, mu\n" \
    "csrw fflags, %[initial]\n" \
    "vfred" STR(OP) ".vs v4, v8, v2, v0.t\n" \
    "vmv.x.s %[result], v4\n csrr %[flags], fflags\n" \
    : [result] "=&r"(result), [flags] "=&r"(flags) \
    : [vl] "r"((uint64_t)vl), [seed] "r"(seed), [initial] "r"((uint64_t)initial_flags), \
      [source] "r"(source.bytes), [mask] "r"(mask) : "t0", "memory"); \
  *r=result; *f=flags; \
}
RUN(16,min) RUN(16,max) RUN(32,min) RUN(32,max) RUN(64,min) RUN(64,max)
typedef void (*runner)(unsigned,uint64_t,unsigned,uint64_t*,uint64_t*);
struct format { unsigned width; uint64_t one,two,snan,qnan,canonical,sign,inf; runner run[2]; };
static const struct format formats[]={
 {16,0x3c00,0x4000,0x7c01,0x7e55,0x7e00,0x8000,0x7c00,{run16min,run16max}},
 {32,0x3f800000,0x40000000,0x7f800001,0x7fc12345,0x7fc00000,0x80000000,0x7f800000,{run32min,run32max}},
 {64,0x3ff0000000000000ULL,0x4000000000000000ULL,0x7ff0000000000001ULL,
  0x7ff8123456789abcULL,0x7ff8000000000000ULL,0x8000000000000000ULL,
  0x7ff0000000000000ULL,{run64min,run64max}}
};
static void put(unsigned w,unsigned i,uint64_t value) {
  for(unsigned b=0;b<w/8;b++) source.bytes[i*(w/8)+b]=(uint8_t)(value>>(8*b));
}
int main(void) {
 unsigned cases=0;
 for(unsigned k=0;k<3;k++) for(unsigned op=0;op<2;op++) for(unsigned t=0;t<23;t++) {
  const struct format *p=&formats[k];
  unsigned vl=128/(p->width/8), initial=0;
  uint64_t seed=p->qnan,want=p->canonical,want_flags=0;
  for(unsigned i=0;i<8;i++) mask[i]=0xff;
  uint64_t packed=p->qnan;
  for(unsigned shift=p->width;shift<64;shift+=p->width)packed|=p->qnan<<shift;
  for(unsigned i=0;i<16;i++)source.words[i]=packed;
  switch(t) {
   case 0: break; // full all-qNaN
   case 1: vl=5; for(unsigned i=0;i<8;i++)mask[i]=0; want=seed; break;
   case 2: vl=15; seed=p->snan; for(unsigned i=0;i<8;i++)mask[i]=0; want=seed; break;
   case 3: vl=1; seed=p->sign; mask[0]=0; want=seed; break;
   case 4: case 5:
    vl=7;mask[0]=8;put(p->width,3,p->one);want=p->one;
    if(t==5) {seed=p->snan;want_flags=16;} break;
   case 6: seed=p->snan;want_flags=16;break;
   case 7: seed=p->two;put(p->width,0,p->snan);want=seed;want_flags=16;break;
   case 8:
    vl=5;mask[0]=8;for(unsigned i=0;i<5;i++)put(p->width,i,p->snan);
    put(p->width,3,p->one);want=p->one;break;
   case 9: case 10:
    vl=t==9?1:5;
    for(unsigned i=vl;i<128/(p->width/8);i++)put(p->width,i,p->snan);
    break;
   case 11: vl=2;seed=0;put(p->width,0,p->sign);put(p->width,1,0);want=op?0:p->sign;break;
   case 12: vl=3;put(p->width,0,p->inf);put(p->width,1,p->inf|p->sign);want=p->inf|(op?0:p->sign);break;
   case 13: seed=p->two;want=seed;break;
   case 14: vl=15;put(p->width,14,p->snan);want_flags=16;break;
   case 15: vl=5;seed=p->one;put(p->width,0,1);put(p->width,4,p->one|p->sign);want=op?p->one:(p->one|p->sign);break;
   case 16: vl=0;seed=p->snan;want=7;break; // VL=0 leaves destination unchanged
   case 18: case 19:
    if(t==19)seed=p->snan;
    for(unsigned i=0;i<8;i++)mask[i]=0;
    want=seed;break;
   case 20:
    seed=p->snan;for(unsigned i=0;i<8;i++)mask[i]=0;
    mask[(vl-1)/8]=1u<<((vl-1)%8);put(p->width,vl-1,p->one);want=p->one;want_flags=16;break;
   case 21: put(p->width,vl-1,p->snan);want_flags=16;break;
   case 22:
    seed=p->two;packed=p->one;
    for(unsigned shift=p->width;shift<64;shift+=p->width)packed|=p->one<<shift;
    for(unsigned i=0;i<16;i++)source.words[i]=packed;
    want=op?p->two:p->one;break;
   case 17: vl=3;initial=2;want_flags=2;break; // retain accrued flags
  }
  uint64_t got,flags;p->run[op](vl,seed,initial,&got,&flags);
  if(p->width<64)got&=(1ULL<<p->width)-1;
  if(got!=want || flags!=want_flags) {
   printf("minmax IEEE FAIL width=%u op=%u case=%u vl=%u got=%lx want=%lx flags=%lx want_flags=%lx\n",p->width,op,t,vl,got,want,flags,want_flags);return 1;
  }
  cases++;
 }
 printf("minmax IEEE PASS: %u cases\n",cases);return 0;
}
