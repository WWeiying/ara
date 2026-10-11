// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint8_t a[128] __attribute__((aligned(128)));
static uint8_t b[128] __attribute__((aligned(128)));
static uint8_t result[128] __attribute__((aligned(128)));
static uint8_t mask[16] __attribute__((aligned(128)));

static void put(uint8_t *p, unsigned n, uint64_t x) {
  for(unsigned j=0;j<n;j++) p[j]=(uint8_t)(x>>(8*j));
}
static uint64_t get(const uint8_t *p, unsigned n) {
  uint64_t x=0;for(unsigned j=0;j<n;j++) x|=(uint64_t)p[j]<<(8*j);return x;
}
#define RUN(OP, BITS) asm volatile( \
    "vsetvli zero,%[n],e" #BITS ",m1,tu,mu\n" \
    "vle" #BITS ".v v4,(%[a])\nvle" #BITS ".v v6,(%[b])\n" \
    "vlm.v v0,(%[mask])\nvmv.v.i v8,0\ncsrwi fflags,0\n" \
    OP "\nvse" #BITS ".v v8,(%[out])\ncsrr %[flags],fflags\n" \
    : [flags] "=&r"(flags) \
    : [n] "r"((uint64_t)n),[a] "r"(a),[b] "r"(b),[mask] "r"(mask),[out] "r"(result) : "memory")
#define CASE(BITS, BYTES, ONE, HALF, FOUR, NEGONE, TWO, SQRT, MODE) do { \
  const unsigned n=128/BYTES; \
  for(unsigned i=0;i<16;i++) mask[i]=MODE==0?0xff:MODE==1?0xaa:0; \
  for(unsigned i=0;i<n;i++) { \
    unsigned active=MODE==0 || (MODE==1 && (i&1)); \
    put(a+i*BYTES,BYTES,active?(SQRT?FOUR:ONE):(SQRT?NEGONE:0)); \
    put(b+i*BYTES,BYTES,active?HALF:0); \
  } \
  uint64_t flags; \
  if(SQRT) { RUN("vfsqrt.v v8,v4,v0.t",BITS); } \
  else { RUN("vfdiv.vv v8,v4,v6,v0.t",BITS); } \
  ++cases; \
  if(flags) {printf("FAIL DIV/SQRT case=%u flags=%lx\n",cases,flags);return 1;} \
  for(unsigned i=0;i<n;i++) { \
    uint64_t expected=(MODE==0 || (MODE==1 && (i&1)))?(TWO):0; \
    uint64_t actual=get(result+i*BYTES,BYTES); \
    if(actual!=expected) {printf("FAIL DIV/SQRT case=%u i=%u got=%lx expected=%lx\n",cases,i,actual,expected);return 1;} \
  } \
} while(0)

#define WIDTHS(SQRT, MODE) do { \
  CASE(16,2,0x3c00,0x3800,0x4400,0xbc00,0x4000,SQRT,MODE); \
  CASE(32,4,0x3f800000,0x3f000000,0x40800000,0xbf800000,0x40000000,SQRT,MODE); \
  CASE(64,8,0x3ff0000000000000ULL,0x3fe0000000000000ULL,0x4010000000000000ULL,0xbff0000000000000ULL,0x4000000000000000ULL,SQRT,MODE); \
} while(0)
int main(void) {
  unsigned cases=0;
  WIDTHS(0,0); WIDTHS(0,1); WIDTHS(0,2);
  WIDTHS(1,0); WIDTHS(1,1); WIDTHS(1,2);
  printf("RCE DIV/SQRT mask PASS: %u FP16/32/64 full-vector value and flag cases\n",cases);
  return 0;
}
