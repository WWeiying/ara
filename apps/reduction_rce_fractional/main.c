// SPDX-License-Identifier: Apache-2.0
// Fractional LMUL source groups with scalar seeds/destinations and mixed execution.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint8_t mask[16] __attribute__((aligned(128)));
static unsigned checks;
static uint64_t width_mask(unsigned bits) { return bits==64?~0ULL:(1ULL<<bits)-1; }
static uint64_t merge(unsigned op,unsigned bits,uint64_t a,uint64_t b) {
  uint64_t m=width_mask(bits);a&=m;b&=m;
  int less=(a<b);
  if(op==5 || op==7) less=((a>>(bits-1))!=(b>>(bits-1))) ? (a>>(bits-1)) : less;
  switch(op) {
    case 1:return a&b; case 2:return a|b; case 3:return a^b;
    case 4:case 5:return less?a:b;case 6:case 7:return less?b:a;
    default:return (a+b)&m;
  }
}
static uint64_t model(unsigned op,unsigned sew,unsigned bits,unsigned vl,unsigned mode) {
  uint64_t a=width_mask(sew)-1,seed=131;
  if(op==9 && (a>>(sew-1))) a|=~width_mask(sew);
  for(unsigned i=0;i<vl;i++) seed=merge(op,bits,seed,a);
  for(unsigned i=0;i<vl;i++) if(mode==0 || (mode==1 && !(i&1))) seed=merge(op,bits,seed,5);
  if(bits<64 && (seed>>(bits-1))) seed|=~width_mask(bits);
  return seed;
}

#define STR1(X) #X
#define STR(X) STR1(X)
#define CASE(SEW,BITS,LMUL,DEN,OP,CODE) do { \
  for(unsigned mode=0;mode<4;mode++) { \
    for(unsigned i=0;i<16;i++) mask[i]=mode==0?255:mode==1?0x55:0; \
    unsigned max=VLEN/(SEW*DEN),vl=mode==0?max:mode==1?max-1:mode==2?1:0; \
    uint64_t result,normal,actual_vl; \
    asm volatile( \
      "vsetivli zero,1,e" STR(BITS) ",m1,tu,mu\nli t0,131\nvmv.s.x v2,t0\n" \
      "li t0,90\nvmv.s.x v3,t0\n" \
      "vsetvli %[actual],%[vl],e" STR(SEW) "," STR(LMUL) ",tu,mu\n" \
      "li t0,-2\nvmv.v.x v4,t0\nvmv.v.i v6,5\nvlm.v v0,(%[mask])\n" \
      "vmv.v.i v14,4\nvmv.v.i v16,5\n" \
      OP " v8,v4,v2\n" \
      "vadd.vv v12,v14,v16\n" \
      OP " v3,v6,v8,v0.t\n" \
      "vmv.x.s %[normal],v12\n" \
      "vsetivli zero,1,e" STR(BITS) ",m1,tu,mu\nvmv.x.s %[r],v3\n" \
      : [r] "=&r"(result),[normal] "=&r"(normal),[actual] "=&r"(actual_vl) \
      : [vl] "r"((uint64_t)vl),[mask] "r"(mask) : "t0","memory"); \
    uint64_t expected=vl?model(CODE,SEW,BITS,vl,mode):90; ++checks; \
    if(actual_vl!=vl || (result&width_mask(BITS))!=(expected&width_mask(BITS)) || \
       (vl && (normal&width_mask(SEW))!=9)) { \
      printf("FAIL fractional " OP " e%u," STR(LMUL) " mode=%u vl=%lu expected_vl=%u result=%lx expected=%lx normal=%lx\n", \
        SEW,mode,actual_vl,vl,result,expected,normal);return 1; \
    } \
  } \
} while(0)

// Exact encodings of the small positive integers used below, without relying
// on the vector datapath or a C floating-point rounding implementation.
static uint64_t fp_integer(unsigned value,unsigned bits) {
  if(!value)return 0;
  unsigned fraction=bits==16?10:bits==32?23:52,bias=bits==16?15:bits==32?127:1023;
  unsigned exponent=0;for(unsigned x=value;x>1;x>>=1)++exponent;
  return ((uint64_t)(bias+exponent)<<fraction) | ((uint64_t)(value-(1U<<exponent))<<(fraction-exponent));
}
#define FPCASE(SEW,BITS,LMUL,DEN,OP,KIND) do { \
  for(unsigned mode=0;mode<4;mode++) { \
    for(unsigned i=0;i<16;i++)mask[i]=mode==0?255:mode==1?0x55:0; \
    unsigned max=VLEN/(SEW*DEN),vl=mode==0?max:mode==1?max-1:mode==2?1:0; \
    unsigned active=mode==0?vl:mode==1?(vl+1)/2:0,seed=KIND==2?0:3; \
    uint64_t result,flags,actual_vl; \
    asm volatile( \
      "vsetivli zero,1,e" STR(BITS) ",m1,tu,mu\nvmv.s.x v2,%[seed]\n" \
      "li t0,90\nvmv.s.x v3,t0\n" \
      "vsetvli %[actual],%[vl],e" STR(SEW) "," STR(LMUL) ",tu,mu\n" \
      "vmv.v.x v4,%[one]\nvmv.v.x v6,%[two]\nvlm.v v0,(%[mask])\n" \
      "csrwi fflags,0\n" OP " v8,v4,v2\n" OP " v3,v6,v8,v0.t\n" \
      "vsetivli zero,1,e" STR(BITS) ",m1,tu,mu\nvmv.x.s %[r],v3\ncsrr %[flags],fflags\n" \
      : [r] "=&r"(result),[flags] "=&r"(flags),[actual] "=&r"(actual_vl) \
      : [vl] "r"((uint64_t)vl),[mask] "r"(mask),[seed] "r"(fp_integer(seed,BITS)), \
        [one] "r"(fp_integer(1,SEW)),[two] "r"(fp_integer(2,SEW)) : "t0","memory"); \
    unsigned n=KIND==0?seed+vl+2*active:KIND==1?1:active?2:1; \
    uint64_t expected=vl?fp_integer(n,BITS):90;++checks; \
    if(actual_vl!=vl || (result&width_mask(BITS))!=expected || flags) { \
      printf("FAIL fractional " OP " e%u," STR(LMUL) " mode=%u vl=%lu result=%lx expected=%lx flags=%lx\n", \
        SEW,mode,actual_vl,result,expected,flags);return 1; \
    } \
  } \
} while(0)
int main(void) {
  CASE(8,8,mf8,8,"vredsum.vs",0);
  CASE(8,8,mf8,8,"vredand.vs",1);
  CASE(8,8,mf8,8,"vredor.vs",2);
  CASE(8,8,mf8,8,"vredxor.vs",3);
  CASE(8,8,mf8,8,"vredminu.vs",4);
  CASE(8,8,mf8,8,"vredmin.vs",5);
  CASE(8,8,mf8,8,"vredmaxu.vs",6);
  CASE(8,8,mf8,8,"vredmax.vs",7);
  CASE(8,16,mf8,8,"vwredsumu.vs",8);
  CASE(8,16,mf8,8,"vwredsum.vs",9);
  CASE(8,8,mf4,4,"vredsum.vs",0);
  CASE(8,8,mf4,4,"vredand.vs",1);
  CASE(8,8,mf4,4,"vredor.vs",2);
  CASE(8,8,mf4,4,"vredxor.vs",3);
  CASE(8,8,mf4,4,"vredminu.vs",4);
  CASE(8,8,mf4,4,"vredmin.vs",5);
  CASE(8,8,mf4,4,"vredmaxu.vs",6);
  CASE(8,8,mf4,4,"vredmax.vs",7);
  CASE(8,16,mf4,4,"vwredsumu.vs",8);
  CASE(8,16,mf4,4,"vwredsum.vs",9);
  CASE(8,8,mf2,2,"vredsum.vs",0);
  CASE(8,8,mf2,2,"vredand.vs",1);
  CASE(8,8,mf2,2,"vredor.vs",2);
  CASE(8,8,mf2,2,"vredxor.vs",3);
  CASE(8,8,mf2,2,"vredminu.vs",4);
  CASE(8,8,mf2,2,"vredmin.vs",5);
  CASE(8,8,mf2,2,"vredmaxu.vs",6);
  CASE(8,8,mf2,2,"vredmax.vs",7);
  CASE(8,16,mf2,2,"vwredsumu.vs",8);
  CASE(8,16,mf2,2,"vwredsum.vs",9);
  CASE(16,16,mf4,4,"vredsum.vs",0);
  CASE(16,16,mf4,4,"vredand.vs",1);
  CASE(16,16,mf4,4,"vredor.vs",2);
  CASE(16,16,mf4,4,"vredxor.vs",3);
  CASE(16,16,mf4,4,"vredminu.vs",4);
  CASE(16,16,mf4,4,"vredmin.vs",5);
  CASE(16,16,mf4,4,"vredmaxu.vs",6);
  CASE(16,16,mf4,4,"vredmax.vs",7);
  CASE(16,32,mf4,4,"vwredsumu.vs",8);
  CASE(16,32,mf4,4,"vwredsum.vs",9);
  CASE(16,16,mf2,2,"vredsum.vs",0);
  CASE(16,16,mf2,2,"vredand.vs",1);
  CASE(16,16,mf2,2,"vredor.vs",2);
  CASE(16,16,mf2,2,"vredxor.vs",3);
  CASE(16,16,mf2,2,"vredminu.vs",4);
  CASE(16,16,mf2,2,"vredmin.vs",5);
  CASE(16,16,mf2,2,"vredmaxu.vs",6);
  CASE(16,16,mf2,2,"vredmax.vs",7);
  CASE(16,32,mf2,2,"vwredsumu.vs",8);
  CASE(16,32,mf2,2,"vwredsum.vs",9);
  CASE(32,32,mf2,2,"vredsum.vs",0);
  CASE(32,32,mf2,2,"vredand.vs",1);
  CASE(32,32,mf2,2,"vredor.vs",2);
  CASE(32,32,mf2,2,"vredxor.vs",3);
  CASE(32,32,mf2,2,"vredminu.vs",4);
  CASE(32,32,mf2,2,"vredmin.vs",5);
  CASE(32,32,mf2,2,"vredmaxu.vs",6);
  CASE(32,32,mf2,2,"vredmax.vs",7);
  CASE(32,64,mf2,2,"vwredsumu.vs",8);
  CASE(32,64,mf2,2,"vwredsum.vs",9);
  FPCASE(16,16,mf4,4,"vfredusum.vs",0);
  FPCASE(16,16,mf4,4,"vfredmin.vs",1);
  FPCASE(16,16,mf4,4,"vfredmax.vs",2);
  FPCASE(16,32,mf4,4,"vfwredusum.vs",0);
  FPCASE(16,16,mf2,2,"vfredusum.vs",0);
  FPCASE(16,16,mf2,2,"vfredmin.vs",1);
  FPCASE(16,16,mf2,2,"vfredmax.vs",2);
  FPCASE(16,32,mf2,2,"vfwredusum.vs",0);
  FPCASE(32,32,mf2,2,"vfredusum.vs",0);
  FPCASE(32,32,mf2,2,"vfredmin.vs",1);
  FPCASE(32,32,mf2,2,"vfredmax.vs",2);
  FPCASE(32,64,mf2,2,"vfwredusum.vs",0);
  printf("RCE fractional LMUL PASS: %u integer/FP opcode, mask and VL cases\n",checks);return 0;
}
