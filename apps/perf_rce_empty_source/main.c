// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
static uint64_t window_cycles[44];
static unsigned window_count;
// Same ELF and timing window for bypass enabled/disabled. Every result is
// checked, including sNaN seed payload preservation and zero FP exceptions.
#define CHECK(OP, SEW, SEED, MASK) do { \
  uint64_t begin, end, got, flags, vl; \
  uint64_t seed = (SEED); \
  asm volatile( \
    "li t0,32\nvsetvli %[vl],t0,e" #SEW ",m1,tu,mu\n" \
    "vmv.v.i v4,1\nvmv.s.x v2,%[seed]\nvmclr.m v0\n" \
    "csrw fflags,zero\ncsrr zero,vstart\nrdcycle %[begin]\n" \
    ".rept 32\n" OP " v8,v4,v2,v0.t\n.endr\n" \
    "vmv.x.s %[got],v8\ncsrr %[flags],fflags\nrdcycle %[end]\n" \
    : [begin] "=&r"(begin), [end] "=&r"(end), [got] "=&r"(got), \
      [flags] "=&r"(flags), [vl] "=&r"(vl) \
    : [seed] "r"(seed) : "t0", "memory"); \
  if ((got & (MASK)) != (seed & (MASK)) || flags) { \
    printf("FAIL empty " OP " e" #SEW " got=%lx seed=%lx flags=%lu\n",got,seed,flags); \
    return 1; \
  } \
  window_cycles[window_count++] = end-begin; \
} while (0)
#define INTEGER(SEW,MASK) \
  CHECK("vredsum.vs",SEW,0xa5,MASK); \
  CHECK("vredand.vs",SEW,0xa5,MASK); \
  CHECK("vredor.vs",SEW,0xa5,MASK); \
  CHECK("vredxor.vs",SEW,0xa5,MASK); \
  CHECK("vredmin.vs",SEW,0xa5,MASK); \
  CHECK("vredmax.vs",SEW,0xa5,MASK); \
  CHECK("vredminu.vs",SEW,0xa5,MASK); \
  CHECK("vredmaxu.vs",SEW,0xa5,MASK)
#define FLOAT(SEW,SNAN,NEGZERO,MASK) \
  CHECK("vfredmin.vs",SEW,SNAN,MASK); \
  CHECK("vfredmax.vs",SEW,SNAN,MASK); \
  CHECK("vfredmin.vs",SEW,NEGZERO,MASK); \
  CHECK("vfredmax.vs",SEW,0,MASK)
int main(void) {
  // Define all preserved tail bytes before the first partial-register write.
  asm volatile("vsetvli t0,zero,e8,m8,tu,mu\n"
    "vmv.v.i v0,0\nvmv.v.i v8,0\nvmv.v.i v16,0\nvmv.v.i v24,0\n"
    ::: "t0", "memory");
  INTEGER(8,0xffULL); INTEGER(16,0xffffULL);
  INTEGER(32,0xffffffffULL); INTEGER(64,~0ULL);
  FLOAT(16,0x7c01ULL,0x8000ULL,0xffffULL);
  FLOAT(32,0x7f800001ULL,0x80000000ULL,0xffffffffULL);
  FLOAT(64,0x7ff0000000000001ULL,0x8000000000000000ULL,~0ULL);
  for (unsigned group=0;group<7;group++) {
    unsigned first = group < 4 ? group*8 : 32+(group-4)*4;
    unsigned count = group < 4 ? 8 : 4;
    uint64_t cycles = 0;
    for(unsigned i=first;i<first+count;i++) cycles += window_cycles[i];
    printf("EMPTY group=%u windows=%u cycles=%lu first_window=%lu\n",group,count,cycles,window_cycles[first]);
  }
  if(window_count != 44) return 1;
  printf("PASS empty-source 44 windows, 1408 reductions\n");
  return 0;
}
