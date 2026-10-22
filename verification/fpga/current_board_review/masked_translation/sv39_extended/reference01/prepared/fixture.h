#ifndef MX_FIXTURE_H
#define MX_FIXTURE_H
#include <stdint.h>
#define MX_N 8
#define MX_G UINT64_C(0xe370697ce370697c)
#define MX_VA UINT64_C(0x40000000)
#define MX_TRAP_MASK UINT64_C(0x8000031888)
enum { UNIT_LOAD, UNIT_STORE, STRIDE_LOAD, STRIDE_STORE, FOF_LOAD };
struct config { int64_t offset, stride; uint64_t op, mask, start, cause, page, vl; };
static const struct config configs[MX_N] = {
  {4090, 2, UNIT_LOAD,   0x24, 5, 13, 1, 8},
  {4090, 2, UNIT_STORE,  0x24, 5, 15, 1, 8},
  {4072, 8, STRIDE_LOAD, 0x24, 5, 13, 1, 8},
  {4106,-4, STRIDE_STORE,0x24, 5, 15, 0, 8},
  {4096, 0, STRIDE_LOAD, 0x24, 2, 13, 1, 8},
  {4096, 0, STRIDE_STORE,0x00, 8,  0, 1, 8},
  {4088, 2, FOF_LOAD,   0xff, 4,  0, 1, 4},
  {4088, 2, FOF_LOAD,   0x0f, 8,  0, 1, 8},
};
struct snapshot { uint64_t lo[8]; uint16_t v[3][64]; uint64_t hi[8]; };
_Static_assert(sizeof(struct snapshot)==512,"snapshot layout");
static unsigned active(unsigned c,unsigned i) { return (configs[c].mask>>i)&1; }
static unsigned store_case(unsigned c) {
  return configs[c].op==UNIT_STORE || configs[c].op==STRIDE_STORE;
}
static unsigned offset(unsigned c,unsigned i) {
  return (unsigned)(configs[c].offset+(int64_t)i*configs[c].stride);
}
static uint16_t original(unsigned c,unsigned half) {
  return (uint16_t)(c>=6 && half>=2044 && half<2048 ?
                    (half-2044)*37+11 : half*37+11);
}
static uint16_t seed(unsigned c,unsigned r,unsigned i) {
  if(r!=1) return (uint16_t)(0x6c00+r*0x100+i);
  return store_case(c) ? (uint16_t)(101+(c==5 ? 0:i*13)) : 0x5b;
}
static uint16_t vector_gold(unsigned c,unsigned phase,unsigned r,unsigned i) {
  if(r!=1 || store_case(c) || i>=8 || !active(c,i)) return seed(c,r,i);
  unsigned stop=phase==1 ? configs[c].start : configs[c].vl;
  return i<stop ? original(c,offset(c,i)/2) : seed(c,r,i);
}
#endif
