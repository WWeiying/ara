#ifndef FOF_TWO_SOURCE_H
#define FOF_TWO_SOURCE_H
#include <stdint.h>
#if SEW == 8
typedef uint8_t word;
#define SCENARIO 0
#define TYPE 0
#define EXPECT_VL 4
#define BASE_OFFSET 4092
#elif SEW == 64
typedef uint64_t word;
#define SCENARIO 5
#define TYPE 24
#define EXPECT_VL 8
#define BASE_OFFSET 4096
#else
#error Only the two admitted source singles are supported
#endif
#define GUARD UINT64_C(0xe370697ce370697c)
#define VA UINT64_C(0x40000000)
#define DONE UINT64_C(0x666f6673696e6701)
#define STATUS_MASK UINT64_C(0x8000031888)
static uint64_t pte(uint64_t address,uint64_t flags) { return (address>>12<<10)|flags; }
static int output_defined(unsigned phase,unsigned i) {
  return !(SEW==8 && phase==1 && i>=5 && i<=8);
}
static word output_gold(unsigned phase,unsigned i) {
  return (word)(SEW==8 && phase==1 && i>=1 && i<=4 ? (i-1)*37+11:0x5b);
}
static uint8_t mask_gold(unsigned i) { return SEW==8 && i==0 ? 255:0; }
static uint64_t page_gold(uint64_t physical,unsigned i) {
  if(SEW==8 && i==511) return UINT64_C(0x7a55300b00000000);
  if(SEW==64 && i>=508 && i<=511) return (i-508)*37+11;
  if(i==1025) return pte(physical+12288,1);
  if(i==1026) return UINT64_C(0x200000cf);
  if(i==1536) return pte(physical+16384,1);
  if(i==2048) return pte(physical,0xc7);
  return 0;
}
#endif
