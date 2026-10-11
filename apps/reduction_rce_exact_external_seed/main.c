// SPDX-License-Identifier: Apache-2.0
// Exact external seeds: raw FP16/FP32, register groups, aliases and masked fallback.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint16_t half_seed[256] __attribute__((aligned(128)));
static uint32_t float_seed[128] __attribute__((aligned(128)));
#define CASE(W,M,N,DATA,ONE,D,S,SEED,EXPECT) do { \
 uint64_t got; \
 asm volatile("li t0," #N "\nvsetvli zero,t0,e" #W ",m" #M ",tu,mu\n" \
 "li t0," #ONE "\nvmv.v.x v4,t0\nvmv.v.i v8,0\ncsrr zero,vstart\n" \
 ".rept 16\nvle" #W ".v v8,(%[p])\nvfredusum.vs " D "," S "," SEED "\n.endr\n" \
 "vmv.x.s %[got]," D "\n" : [got] "=&r"(got) : [p] "r"(DATA) : "t0","memory"); \
 if ((got & ((1ULL<<W)-1)) != (EXPECT)) { \
 printf("FAIL exact external e" #W " m" #M " got=%lx expected=%lx\n",got,(uint64_t)(EXPECT));return 1;} \
} while(0)
int main(void) {
 for(unsigned i=0;i<256;i++) half_seed[i]=0x4200;
 for(unsigned i=0;i<128;i++) float_seed[i]=0x40400000;
 asm volatile("fence rw,rw\nvsetvli t0,zero,e8,m8,tu,mu\nvmv.v.i v0,0\nvmv.v.i v8,0\nvmv.v.i v16,0\nvmv.v.i v24,0\n" ::: "t0","memory");
 CASE(16,1,1,half_seed,0x3c00,"v16","v4","v8",0x4400);
 CASE(16,1,16,half_seed,0x3c00,"v16","v4","v8",0x4cc0);
 CASE(16,2,128,half_seed,0x3c00,"v16","v4","v8",0x5818);
 CASE(32,1,16,float_seed,0x3f800000,"v16","v4","v8",0x41980000);
 CASE(32,4,128,float_seed,0x3f800000,"v16","v4","v8",0x43030000);
 CASE(32,4,128,float_seed,0x3f800000,"v16","v4","v9",0x43030000);
 CASE(32,4,128,float_seed,0x3f800000,"v16","v8","v8",0x43c18000);
 CASE(32,4,128,float_seed,0x3f800000,"v8","v4","v8",0x43030000);
 uint64_t a,b;
 asm volatile("li t0,16\nvsetvli zero,t0,e32,m1,tu,mu\n"
 "li t0,0x3f800000\nvmv.v.x v4,t0\nli t0,0x40e00000\nvmv.v.x v8,t0\nvmclr.m v0\n"
 "vle32.v v8,(%[p]),v0.t\nvfredusum.vs v16,v4,v8\nvmv.x.s %[a],v16\n"
 "li t0,0x40400000\nvmv.v.x v12,t0\nli t0,0x40e00000\nvmv.v.x v8,t0\n"
 "vslidedown.vi v8,v12,1,v0.t\nvfredusum.vs v16,v4,v8\nvmv.x.s %[b],v16\n"
 : [a] "=&r"(a),[b] "=&r"(b) : [p] "r"(float_seed) : "t0","memory");
 if((uint32_t)a!=0x41b80000 || (uint32_t)b!=0x41b80000) {printf("FAIL exact masked external a=%lx b=%lx\n",a,b);return 2;}
 printf("PASS exact external seed: FP16/FP32, LMUL, interior seed, source RAW, destination WAW, masked fallback\n");
 return 0;
}
