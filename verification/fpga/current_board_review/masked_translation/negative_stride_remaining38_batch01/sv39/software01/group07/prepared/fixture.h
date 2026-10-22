#ifndef NS_BATCH_FIXTURE_H
#define NS_BATCH_FIXTURE_H
#include <stdint.h>
#include "cases.h"
#define GUARD UINT64_C(0xe370697ce370697c)
#define VA UINT64_C(0x40000000)
#define DONE UINT64_C(0x6e65677376333938)
#define STATUS_MASK (UINT64_C(0x8000031888) | UINT64_C(0xc0000))
#define NCASES (sizeof(ns_cases)/sizeof(ns_cases[0]))
struct snapshot { uint64_t lo[8]; uint16_t v[3][64]; uint64_t hi[8]; };
_Static_assert(sizeof(struct snapshot)==512,"snapshot layout");
static unsigned active(const struct ns_case *t,unsigned i) { return (t->mask>>(i%8))&1; }
static unsigned address(const struct ns_case *t,unsigned i) { return t->base+(int)i*t->stride; }
static uint16_t original(unsigned h) { return (uint16_t)(h*37+11); }
static unsigned slot_at(const struct ns_case *t,unsigned h) {
  for(unsigned i=0;i<8;++i) if(address(t,i)==2*h) return i;
  return 8;
}
static uint16_t vector_gold(const struct ns_case *t,unsigned phase,unsigned r,unsigned i) {
  if(r!=1) return (uint16_t)(0x6c00+256*r+i);
  if(t->store) return (uint16_t)(101+13*i);
  if(phase && i<8 && active(t,i) && (phase==3 || i<(unsigned)t->start))
    return original(address(t,i)/2);
  return 0x5b;
}
static uint16_t memory_gold(const struct ns_case *t,unsigned phase,unsigned h) {
  uint16_t value=original(h);
  unsigned i=slot_at(t,h);
  if(phase && i<8 && active(t,i)) {
    if(t->store && (i<(unsigned)t->start || phase==3)) value=(uint16_t)(101+13*i);
    if(phase>=2 && t->faults && i<(unsigned)t->start) value^=0x5b;
  }
  return value;
}
static unsigned pending_memory(const struct ns_case *t,unsigned phase,unsigned h) {
  unsigned i=slot_at(t,h);
  return t->store && t->faults && i<8 && i>=(unsigned)t->start && active(t,i) &&
    (phase==1 || (phase==2 && !t->unmapped));
}
#endif
