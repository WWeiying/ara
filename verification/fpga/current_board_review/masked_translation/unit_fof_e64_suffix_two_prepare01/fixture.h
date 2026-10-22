#ifndef UNIT_FOF_E64_SUFFIX_H
#define UNIT_FOF_E64_SUFFIX_H
#include <stdint.h>
#if SEW != 64 || (SCENARIO != 1 && SCENARIO != 2)
#error Only the two original e64 masked-suffix singles
#endif
typedef uint64_t word;
#define TYPE 24
#define EXPECT_VL 8
#define GUARD UINT64_C(0xe370697ce370697c)
#define VA UINT64_C(0x40000000)
#define DONE UINT64_C(0x666f6673696e6701)
#define STATUS_MASK UINT64_C(0x8000031888)
static uint64_t pte(uint64_t address,uint64_t flags) { return (address>>12<<10)|flags; }
static int output_defined(unsigned phase,unsigned i) { (void)phase; (void)i; return 1; }
static word output_gold(unsigned phase,unsigned i) {
  return phase==1 && i>=1 && i<=4 ? (word)((i-1)*37+11) : (word)0x5b;
}
static uint8_t mask_gold(unsigned i) { return i==0 ? 15 : 0; }
static uint64_t page_gold(uint64_t physical,unsigned i) {
  if(i>=508 && i<=511) return (i-508)*37+11;
  if(i==1025) return pte(physical+12288,1);
  if(i==1026) return UINT64_C(0x200000cf);
  if(i==1536) return pte(physical+16384,1);
  if(i==2048) return pte(physical,0xc7);
  return 0;
}
#endif
