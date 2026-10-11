// SPDX-License-Identifier: Apache-2.0
// External seed writes: widths, interior registers, RAW/WAW and masked fallback.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint8_t d8[32] __attribute__((aligned(128)));
static uint16_t d16[32] __attribute__((aligned(128)));
static uint32_t d32[64] __attribute__((aligned(128)));
static uint64_t d64[64] __attribute__((aligned(128)));
#define LOAD_CASE(W,M,N,DATA,D,S,SEED,EXPECT) do { \
 uint64_t got; \
 asm volatile("li t0," #N "\nvsetvli zero,t0,e" #W ",m" #M ",tu,mu\n" \
  "vmv.v.i v4,1\nvmv.v.i v8,7\ncsrr zero,vstart\n" \
  ".rept 8\nvle" #W ".v v8,(%[p])\nvredsum.vs " D "," S "," SEED "\n.endr\n" \
  "vmv.x.s %[got]," D "\n" : [got] "=&r"(got) : [p] "r"(DATA) : "t0","memory"); \
 if(got!=(EXPECT)){printf("FAIL external load e" #W " m" #M " got=%lu expected=%lu\n",got,(uint64_t)(EXPECT));return 1;} \
} while(0)
int main(void) {
 for(unsigned i=0;i<32;i++){d8[i]=3;d16[i]=3;}
 for(unsigned i=0;i<64;i++){d32[i]=3;d64[i]=3;}
 asm volatile("fence rw,rw\nvsetvli t0,zero,e8,m8,tu,mu\nvmv.v.i v0,0\nvmv.v.i v8,0\nvmv.v.i v16,0\nvmv.v.i v24,0\n" ::: "t0","memory");
 LOAD_CASE(8,1,16,d8,"v16","v4","v8",19);
 LOAD_CASE(16,1,16,d16,"v16","v4","v8",19);
 LOAD_CASE(32,2,64,d32,"v16","v4","v8",67);
 LOAD_CASE(64,4,64,d64,"v16","v4","v8",67);
 LOAD_CASE(32,2,64,d32,"v16","v4","v9",67);
 LOAD_CASE(64,4,64,d64,"v16","v4","v10",67);
 LOAD_CASE(64,4,64,d64,"v16","v8","v8",195);
 LOAD_CASE(64,4,64,d64,"v8","v4","v8",67);
 uint64_t a,b;
 asm volatile("li t0,16\nvsetvli zero,t0,e64,m1,tu,mu\n"
  "vmv.v.i v4,1\nvmv.v.i v8,7\nvmclr.m v0\n"
  "vle64.v v8,(%[p]),v0.t\nvredsum.vs v16,v4,v8\nvmv.x.s %[a],v16\n"
  "vmv.v.i v12,3\nvmv.v.i v8,7\n"
  "vslidedown.vi v8,v12,1,v0.t\nvredsum.vs v16,v4,v8\nvmv.x.s %[b],v16\n"
  : [a] "=&r"(a),[b] "=&r"(b) : [p] "r"(d64) : "t0","memory");
 if(a!=23 || b!=23){printf("FAIL masked external seed a=%lu b=%lu\n",a,b);return 2;}
 printf("PASS external seed: four widths, LMUL, interior seed, source RAW, destination WAW, masked Load/Slide\n");
 return 0;
}
