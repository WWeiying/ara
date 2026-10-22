#ifndef SMALL_EXCEPTIONS_REMAINING14_H
#define SMALL_EXCEPTIONS_REMAINING14_H
#include <stdint.h>
#if SEW == 8
typedef uint8_t word;
#define TYPE 0
#elif SEW == 16
typedef uint16_t word;
#define TYPE 8
#elif SEW == 32
typedef uint32_t word;
#define TYPE 16
#else
#error Unsupported source width
#endif
#if (SCENARIO != 0 && SCENARIO != 1 && SCENARIO != 2 && SCENARIO != 3 && SCENARIO != 5) || (SEW == 8 && SCENARIO == 0)
#error Not a member of the remaining14 source scope
#endif
#define EXPECT_VL (SCENARIO == 0 ? 4 : 8)
#define GUARD UINT64_C(0xe370697ce370697c)
#define VA UINT64_C(0x40000000)
#define DONE UINT64_C(0x666f6673696e6701)
#define STATUS_MASK UINT64_C(0x8000031888)
static uint64_t pte(uint64_t address,uint64_t flags) { return (address>>12<<10)|flags; }
static int output_defined(unsigned phase,unsigned i) {
  return !(SCENARIO == 0 && phase == 1 && i >= 5 && i <= 8);
}
static word output_gold(unsigned phase,unsigned i) {
  return SCENARIO < 3 && phase == 1 && i >= 1 && i <= 4 ? (word)((i-1)*37+11) : (word)0x5b;
}
static uint8_t mask_gold(unsigned i) {
  return i ? 0 : SCENARIO == 0 ? 255 : SCENARIO == 1 || SCENARIO == 2 ? 15 : 0;
}
static uint64_t page_gold(uint64_t physical,unsigned i) {
  if(i >= (4096-4*sizeof(word))/8 && i < 512) {
    uint64_t value=0;
    for(unsigned j=0;j<4;++j) {
      unsigned offset=4096-4*sizeof(word)+j*sizeof(word);
      if(offset/8 == i) value |= (uint64_t)(word)(j*37+11) << ((offset%8)*8);
    }
    return value;
  }
  if(i==1025) return pte(physical+12288,1);
  if(i==1026) return UINT64_C(0x200000cf);
  if(i==1536) return pte(physical+16384,1);
  if(i==2048) return pte(physical,0xc7);
  return 0;
}
#endif
