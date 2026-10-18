// SPDX-License-Identifier: Apache-2.0
// Exact seed-window fallback latency. Integer-only expected data/flags.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
#include "oracle.h"

static uint32_t input[32] __attribute__((aligned(128)));

#define TIMED_REDUCTION(SEEDREG) \
  asm volatile( \
    "vadd.vi v8,v8,0\ncsrwi fflags,0\ncsrr zero,vstart\n" \
    "rdcycle %[start]\nvfredusum.vs v16,v8," SEEDREG "\n" \
    "vmv.x.s %[result],v16\nrdcycle %[end]\ncsrr %[flags],fflags\n" \
    : [start] "=&r"(start),[end] "=&r"(end), \
      [result] "=&r"(result),[flags] "=&r"(flags) :: "memory")

static int probe(unsigned scenario,unsigned chain) {
  // EW32 maps lane=index%4. Cancellation uses +1 and -1 in each lane.
  for(unsigned i=0;i<32;i++)
    input[i]=scenario==0 ? 0 : scenario==1 ?
      (i<4 ? 0x3f800000U : i<8 ? 0xbf800000U : 0) :
      scenario==2 ? 1U : 0x3f800000U;
  const uint64_t seed=scenario<2 ? 0x40400000U : scenario==2 ? 0x3f800000U : 1U;
  uint64_t vl,start,end,result=0,flags=0,cycles=0,flags_or=0;
  unsigned failed=0;
  asm volatile("li t0,32\nvsetvli %[vl],t0,e32,m1,tu,mu\n"
    "vle32.v v8,(%[src])\nvmv.s.x v2,%[seed]\nvmv.s.x v16,%[seed]\ncsrwi frm,0\n"
    : [vl] "=&r"(vl) : [src] "r"(input),[seed] "r"(seed) : "t0","memory");
  for(unsigned iteration=0;iteration<8;iteration++) {
    if(chain) { TIMED_REDUCTION("v16"); }
    else { TIMED_REDUCTION("v2"); }
    cycles+=end-start;flags_or|=flags;
    if(vl!=32 || (uint32_t)result!=expected[scenario][chain][iteration].bits ||
       flags!=expected[scenario][chain][iteration].flags) {
      printf("EXACT_SEED_FALLBACK_FAIL scenario=%u chain=%u iteration=%u vl=%lu result=%lx expected=%x flags=%lx expected_flags=%x\n",
        scenario,chain,iteration,vl,result,expected[scenario][chain][iteration].bits,
        flags,expected[scenario][chain][iteration].flags);
      failed=1;
    }
  }
  printf("EXACT_SEED_FALLBACK scenario=%u chain=%u vl=%lu reductions=8 cycles=%lu result=%lx flags=%lx flags_or=%lx %s\n",
    scenario,chain,vl,cycles,result,flags,flags_or,failed?"FAIL":"PASS");
  return failed;
}

int main(void) {
  unsigned failures=0;
  asm volatile("vsetvli t0,zero,e8,m8,tu,mu\nvmv.v.i v0,0\n"
               "vmv.v.i v8,0\nvmv.v.i v16,0\nvmv.v.i v24,0\n"
               ::: "t0","memory");
  for(unsigned scenario=0;scenario<4;scenario++)
    for(unsigned chain=0;chain<2;chain++) failures+=probe(scenario,chain);
  printf("EXACT_SEED_FALLBACK_DONE cases=8 %s\n",failures?"FAIL":"PASS");
  return failures!=0;
}
