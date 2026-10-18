// SPDX-License-Identifier: Apache-2.0
// Four-lane exact-state transport stress. No host floating-point oracle.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"

static uint32_t input[32] __attribute__((aligned(128)));

static uint32_t power_bits(int exponent) {
  return exponent == -149 ? 1U : (uint32_t)(exponent + 127) << 23;
}

static void prepare(unsigned full288) {
  // EW32 shuffle_index stripes FP32 elements over lanes: lane = index % 4.
  // Each lane has a nonzero bit in every transported 64-bit magnitude limb.
  // +/- lane pairs cancel every large AND tiny term exactly, leaving four 1s.
  const int exponents[5] = {-149, -80, -16, 48, full288 ? 120 : 80};
  for (unsigned i=0;i<32;i++) input[i]=0;
  for (unsigned lane=0;lane<4;lane++) {
    for (unsigned term=0;term<5;term++) {
      unsigned index=term*4+lane;
      input[index]=power_bits(exponents[term]) | (lane>=2 ? 0x80000000U : 0);
    }
    input[20+lane]=0x3f800000U;
  }
}

static int probe(unsigned full288, unsigned chain) {
  uint64_t actual_vl, result, flags, start, end;
  prepare(full288);
  asm volatile(
    "li t0,32\nvsetvli %[actual_vl],t0,e32,m1,tu,mu\n"
    "vle32.v v8,(%[src])\n"
    "li t0,0x40400000\nvmv.s.x v2,t0\nvmv.s.x v16,t0\n"
    "csrwi frm,0\ncsrwi fflags,0\n"
    // vstart CSR read serializes source/seed setup before the measured window.
    "csrr zero,vstart\nrdcycle %[start]\n"
    "beqz %[chain],1f\n"
    // Every seed is the previous reduction result, exercising late seed RAW.
    ".rept 16\nvfredusum.vs v16,v8,v16\n.endr\nj 2f\n"
    "1:\n"
    // Numerically inert writes advance source versions; repeated independent
    // reductions cannot use a cached result from an unchanged source version.
    ".rept 16\nvadd.vi v8,v8,0\nvfredusum.vs v16,v8,v2\n.endr\n"
    "2: vmv.x.s %[result],v16\nrdcycle %[end]\ncsrr %[flags],fflags\n"
    : [actual_vl] "=&r"(actual_vl), [result] "=&r"(result),
      [flags] "=&r"(flags), [start] "=&r"(start), [end] "=&r"(end)
    : [src] "r"(input), [chain] "r"((uint64_t)chain)
    : "t0", "memory");
  // Exact real sum: two +T and two -T for each exponent, plus four ones.
  // Ordinary: 3+4=7 (0x40e00000); chain: 3+16*4=67 (0x42860000).
  // All results are exactly representable, so every fflag must stay clear.
  uint32_t expected=chain ? 0x42860000U : 0x40e00000U;
  int failed=actual_vl!=32 || (uint32_t)result!=expected || flags!=0;
  printf("EXACT_DENSE_SEED full288=%u end=%u chain=%u vl=%lu reductions=16 source_rewrites=%u cycles=%lu result=%lx expected=%x flags=%lx %s\n",
         full288,full288?5:4,chain,actual_vl,chain?0:16,end-start,
         result,expected,flags,failed?"FAIL":"PASS");
  return failed;
}


#define SERIAL_REDUCE(SEEDREG) \
  asm volatile( \
    "vadd.vi v8,v8,0\ncsrr zero,vstart\n" \
    "rdcycle %[start]\nvfredusum.vs v16,v8," SEEDREG "\n" \
    "vmv.x.s %[result],v16\nrdcycle %[end]\ncsrr %[flags],fflags\n" \
    : [start] "=&r"(start),[end] "=&r"(end), \
      [result] "=&r"(result),[flags] "=&r"(flags) :: "memory")

static int serialized(unsigned full288,unsigned chain) {
  uint64_t actual_vl,start,end,result=0,flags=0,total=0;
  unsigned failed=0;
  prepare(full288);
  asm volatile("li t0,32\nvsetvli %[vl],t0,e32,m1,tu,mu\n"
    "vle32.v v8,(%[src])\nli t0,0x40400000\n"
    "vmv.s.x v2,t0\nvmv.s.x v16,t0\ncsrwi frm,0\ncsrwi fflags,0\n"
    : [vl] "=&r"(actual_vl) : [src] "r"(input) : "t0","memory");
  for(unsigned iteration=0;iteration<16;iteration++) {
    if(chain) { SERIAL_REDUCE("v16"); }
    else { SERIAL_REDUCE("v2"); }
    total+=end-start;
    // 3+4*k, k=1..16, are exact integers; encode via integer normalization.
    unsigned value=chain ? 3+4*(iteration+1) : 7;
    unsigned msb=0;
    for(unsigned n=value;n>1;n>>=1) msb++;
    uint32_t expected=((msb+127)<<23)|((value<<(23-msb))&0x7fffffU);
    if(actual_vl!=32 || (uint32_t)result!=expected || flags) failed=1;
  }
  printf("EXACT_DENSE_SERIAL full288=%u end=%u chain=%u vl=%lu reductions=16 source_rewrites=16 cycles=%lu result=%lx flags=%lx %s\n",
    full288,full288?5:4,chain,actual_vl,total,result,flags,failed?"FAIL":"PASS");
  return failed;
}

int main(void) {
  unsigned failed=0;
  // Initialize all vector state with legal aligned m8 groups, like other probes.
  asm volatile("vsetvli t0,zero,e8,m8,tu,mu\nvmv.v.i v0,0\n"
               "vmv.v.i v8,0\nvmv.v.i v16,0\nvmv.v.i v24,0\n"
               ::: "t0","memory");
  for(unsigned full=0;full<2;full++)
    for(unsigned chain=0;chain<2;chain++) failed+=probe(full,chain);
  for(unsigned full=0;full<2;full++)
    for(unsigned chain=0;chain<2;chain++) failed+=serialized(full,chain);
  printf("EXACT_DENSE_LATENCY_DONE cases=8 %s\n",failed?"FAIL":"PASS");
  return failed!=0;
}
