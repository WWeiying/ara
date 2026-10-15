#ifndef NEGATIVE_STRIDE_SINGLE_H
#define NEGATIVE_STRIDE_SINGLE_H
#include <stdint.h>
#define GUARD UINT64_C(0xe370697ce370697c)
#define VA UINT64_C(0x40000000)
#define DONE UINT64_C(0x6e65677376333902)
#define STATUS_MASK UINT64_C(0x8000031888)
struct snapshot { uint64_t lo[8]; uint16_t v[3][64]; uint64_t hi[8]; };
_Static_assert(sizeof(struct snapshot)==512,"snapshot layout");
static unsigned active(unsigned i) { return (0x24u>>(i%8))&1; }
static unsigned address(unsigned i) { return 4118-8*i; }
static uint16_t original(unsigned half) { return (uint16_t)(half*37+11); }
static uint16_t vector_gold(unsigned phase,unsigned r,unsigned i) {
  if(r!=1) return (uint16_t)(0x6c00+256*r+i);
  (void)phase;
  return (uint16_t)(101+13*i);
}
static uint16_t memory_gold(unsigned phase,unsigned half) {
  uint16_t value=original(half);
  if(phase==0) return value;
  if(phase==1) return half==address(2)/2 ? 127:value;
  // Keep the original logical-element search, including inactive addresses.
  unsigned slot=8;
  for(unsigned i=0;i<8;++i) if(address(i)==2*half) { slot=i; break; }
  if(slot<8 && active(slot)) {
    if(slot<5) value=(uint16_t)((101+13*slot)^0x5b);
    else if(phase==3) value=(uint16_t)(101+13*slot);
  }
  return value;
}
#endif
