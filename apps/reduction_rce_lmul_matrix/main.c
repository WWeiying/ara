// SPDX-License-Identifier: Apache-2.0
// Unaligned scalar reduction registers, long LMUL sources and neighbor layout.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint8_t neighbor[128] __attribute__((aligned(128)));

#define CASE(SEW, LMUL, VL, RSEW, SOURCE, SEED, OP, EXPECTED) do { \
  uint64_t result, flags; \
  asm volatile( \
    "li t0,128\nvsetvli zero,t0,e8,m1,tu,mu\n" \
    "li t0,0x5a\nvmv.v.x v3,t0\nvid.v v4\n" \
    "vsetivli zero,1," RSEW ",m1,tu,mu\n" \
    "li t0," SEED "\nvmv.s.x v2,t0\n" \
    "li t0," VL "\nvsetvli zero,t0," SEW "," LMUL ",tu,mu\n" \
    "li t0," SOURCE "\nvmv.v.x v8,t0\ncsrwi fflags,0\n" \
    OP " v3,v8,v2\n" \
    "vsetivli zero,1," RSEW ",m1,tu,mu\n" \
    "vmv.x.s %[result],v3\ncsrr %[flags],fflags\n" \
    "li t0,128\nvsetvli zero,t0,e8,m1,tu,mu\n" \
    "vse8.v v4,(%[out])\ncsrr zero,vl\n" \
    : [result] "=&r"(result),[flags] "=&r"(flags) \
    : [out] "r"(neighbor) : "t0","memory"); \
  ++cases; \
  if(result!=(uint64_t)(EXPECTED) || flags) { \
    printf("FAIL LMUL case=%u " OP " " SEW "," LMUL " result=%lx expected=%lx flags=%lx\n",cases,result,(uint64_t)(EXPECTED),flags);return 1; \
  } \
  for(unsigned i=0;i<128;i++) if(neighbor[i]!=i) { \
    printf("FAIL LMUL neighbor case=%u byte=%u got=%u\n",cases,i,neighbor[i]);return 1; \
  } \
} while(0)

int main(void) {
  unsigned cases=0;
  CASE("e64","m1","13","e64","0x3ff0000000000000","0x4008000000000000","vfredusum.vs",0x4030000000000000ULL);
  CASE("e64","m2","29","e64","0x3ff0000000000000","0x4008000000000000","vfredusum.vs",0x4040000000000000ULL);
  CASE("e64","m4","49","e64","0x3ff0000000000000","0x4008000000000000","vfredusum.vs",0x404a000000000000ULL);
  CASE("e64","m8","125","e64","0x3ff0000000000000","0x4008000000000000","vfredusum.vs",0x4060000000000000ULL);
  CASE("e64","m4","49","e64","0x3ff0000000000000","0x4008000000000000","vfredmin.vs",0x3ff0000000000000ULL);
  CASE("e32","m4","125","e32","0x3f800000","0x40400000","vfredusum.vs",0x43000000);
  CASE("e32","m8","253","e32","0x3f800000","0x40400000","vfredusum.vs",0x43800000);
  CASE("e32","m4","125","e32","1","3","vredsum.vs",128);
  CASE("e16","m4","201","e32","1","3","vwredsum.vs",204);
  CASE("e16","m8","401","e32","1","3","vwredsumu.vs",404);
  CASE("e32","m4","125","e64","0x3f800000","0x4008000000000000","vfwredusum.vs",0x4060000000000000ULL);
  CASE("e32","m8","253","e64","0x3f800000","0x4008000000000000","vfwredusum.vs",0x4070000000000000ULL);
  printf("RCE LMUL matrix PASS: %u scalar-register and source-group cases\n",cases);
  return 0;
}
