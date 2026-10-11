// SPDX-License-Identifier: Apache-2.0
// Independent modular integer model; seed chains cover every integer reduction.
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
#define CASE(SEW,BITS,OP,CODE) do { \
  for(unsigned mode=0;mode<3;mode++) { \
    for(unsigned i=0;i<16;i++) mask[i]=mode==0?255:mode==1?0x55:0; \
    unsigned vl=SEW==64?13:17; uint64_t result; \
    asm volatile( \
      "vsetivli zero,1,e" STR(BITS) ",m1,tu,mu\nli t0,131\nvmv.s.x v2,t0\n" \
      "vsetvli zero,%[vl],e" STR(SEW) ",m1,tu,mu\n" \
      "li t0,-2\nvmv.v.x v4,t0\nvmv.v.i v6,5\nvlm.v v0,(%[mask])\n" \
      OP " v8,v4,v2\n" OP " v10,v6,v8,v0.t\n" \
      "vsetivli zero,1,e" STR(BITS) ",m1,tu,mu\nvmv.x.s %[r],v10\n" \
      : [r] "=&r"(result) : [vl] "r"((uint64_t)vl),[mask] "r"(mask) : "t0","memory"); \
    uint64_t expected=model(CODE,SEW,BITS,vl,mode); ++checks; \
    if(result!=expected) { printf("FAIL integer late seed " OP " sew=%u mode=%u got=%lx expected=%lx\n",SEW,mode,result,expected);return 1; } \
  } \
} while(0)
int main(void) {
  CASE(8,8,"vredsum.vs",0);
  CASE(16,16,"vredsum.vs",0);
  CASE(32,32,"vredsum.vs",0);
  CASE(64,64,"vredsum.vs",0);
  CASE(8,8,"vredand.vs",1);
  CASE(16,16,"vredand.vs",1);
  CASE(32,32,"vredand.vs",1);
  CASE(64,64,"vredand.vs",1);
  CASE(8,8,"vredor.vs",2);
  CASE(16,16,"vredor.vs",2);
  CASE(32,32,"vredor.vs",2);
  CASE(64,64,"vredor.vs",2);
  CASE(8,8,"vredxor.vs",3);
  CASE(16,16,"vredxor.vs",3);
  CASE(32,32,"vredxor.vs",3);
  CASE(64,64,"vredxor.vs",3);
  CASE(8,8,"vredminu.vs",4);
  CASE(16,16,"vredminu.vs",4);
  CASE(32,32,"vredminu.vs",4);
  CASE(64,64,"vredminu.vs",4);
  CASE(8,8,"vredmin.vs",5);
  CASE(16,16,"vredmin.vs",5);
  CASE(32,32,"vredmin.vs",5);
  CASE(64,64,"vredmin.vs",5);
  CASE(8,8,"vredmaxu.vs",6);
  CASE(16,16,"vredmaxu.vs",6);
  CASE(32,32,"vredmaxu.vs",6);
  CASE(64,64,"vredmaxu.vs",6);
  CASE(8,8,"vredmax.vs",7);
  CASE(16,16,"vredmax.vs",7);
  CASE(32,32,"vredmax.vs",7);
  CASE(64,64,"vredmax.vs",7);
  CASE(8,16,"vwredsumu.vs",8);
  CASE(16,32,"vwredsumu.vs",8);
  CASE(32,64,"vwredsumu.vs",8);
  CASE(8,16,"vwredsum.vs",9);
  CASE(16,32,"vwredsum.vs",9);
  CASE(32,64,"vwredsum.vs",9);
  printf("RCE integer seed matrix PASS: %u opcode/SEW/Mask chains\n",checks);return 0;
}
