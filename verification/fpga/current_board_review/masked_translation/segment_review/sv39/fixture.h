#ifndef SEGMENT_FIXTURE_H
#define SEGMENT_FIXTURE_H
#include <stdint.h>
#define MX_N 4
#define MX_G UINT64_C(0xe370697ce370697c)
#define MX_VA UINT64_C(0x40000000)
#define MX_TRAP_MASK UINT64_C(0x8000031888)
struct config { unsigned base, store, fault_field; };
static const struct config configs[MX_N] = {
  {4082,0,0}, {4082,1,0}, {4074,0,1}, {4074,1,1}
};
struct snapshot { uint64_t lo[8]; uint16_t v[4][64]; uint64_t hi[8]; };
_Static_assert(sizeof(struct snapshot)==640,"assembly snapshot stride");
static unsigned active(unsigned i) { return (0x24u>>i)&1; }
static unsigned offset(unsigned c,unsigned i,unsigned f) { return configs[c].base+4*i+2*f; }
static uint16_t original(unsigned half) { return (uint16_t)(half*37+11); }
static uint16_t seed(unsigned c,unsigned r,unsigned i) {
  if(r==0 || r==3) return (uint16_t)(0x6c00+r*256+i);
  return configs[c].store ? (uint16_t)(101+13*i+29*(r-1)) : 0x5b;
}
static unsigned partial_vector(unsigned c,unsigned phase,unsigned r,unsigned i) {
  return phase==1 && !configs[c].store && (r==1 || r==2) && i==5;
}
static uint16_t vector_gold(unsigned c,unsigned phase,unsigned r,unsigned i) {
  if((r==1 || r==2) && !configs[c].store && i<8 && active(i) && (phase==2 || i<5))
    return original(offset(c,i,r-1)/2);
  return seed(c,r,i);
}
static unsigned partial_memory(unsigned c,unsigned phase,unsigned half) {
  return phase==1 && configs[c].store && c==3 && half==offset(c,5,0)/2;
}
static uint16_t memory_gold(unsigned c,unsigned phase,unsigned half) {
  unsigned delta=half*2-configs[c].base;
  if(delta<32) {
    unsigned i=delta/4,f=(delta%4)/2;
    if(!active(i)) return original(half);
    uint16_t value=configs[c].store ? seed(c,f+1,i) : original(half);
    if(phase==2 && i<5) return value^0x5b;
    if(configs[c].store && (phase==2 || i<5)) return value;
  }
  return original(half);
}
#endif
