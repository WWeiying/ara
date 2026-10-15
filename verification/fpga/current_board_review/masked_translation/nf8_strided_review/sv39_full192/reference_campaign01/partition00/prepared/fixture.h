#include <stdint.h>
#define NA_VA UINT64_C(0x40000000)
#define NA_G UINT64_C(0xe370697ce370697c)
#define NA_TM UINT64_C(0x8000031888)
#define NA_DONE UINT64_C(0x6e3866756c6c0004)
#ifndef NA_GROUP
#define NA_GROUP 0
#endif
_Static_assert(NA_GROUP>=0 && NA_GROUP<48,"fixed original group");
struct config { unsigned unmapped,store,boundary,mode,gap,split,mask,base,start,stride; };
struct snapshot { uint64_t lo[8]; uint32_t v[10][32]; uint64_t hi[8]; };
_Static_assert(sizeof(struct snapshot)==1408,"snapshot ABI");
static struct config config(unsigned t) {
  struct config c;
  c.split=t%2; t/=2; c.gap=1+2*(t%2); t/=2; c.mode=t%4; t/=4;
  c.boundary=1+2*(t%3); t/=3; c.store=t%2; c.unmapped=t/2;
  c.mask=c.mode==0 ? 255:c.mode==1 ? 170:c.mode==2 ? 36:0;
  c.stride=4*(8+c.gap);
  c.base=4096-c.boundary*c.stride-16*c.split;
  c.start=8;
  for(unsigned i=c.boundary;i<8;++i) if((c.mask>>i)&1) { c.start=i; break; }
  return c;
}
static unsigned active(struct config c,unsigned i) { return (c.mask>>i)&1; }
static unsigned field_offset(struct config c,unsigned i,unsigned f) {
  return c.base+i*c.stride+4*f;
}
static uint32_t original(unsigned byte) { return byte/4*37+11; }
static uint32_t input(unsigned f,unsigned i) { return 101+i*13+f*29; }
static uint32_t seed(unsigned r,unsigned i) { return 0x6c800000u^(r<<16)^i; }
static uint32_t vector_gold(struct config c,unsigned phase,unsigned r,unsigned i,int *strict) {
  *strict=1;
  if(r<2 || i>=16) return seed(r,i);
  if(c.store) return input(r-2,i);
  if(i>=8 || !active(c,i)) return 0x5b;
  if(phase==1 && i>=c.start) { *strict=0; return 0; }
  return original(field_offset(c,i,r-2));
}
static inline uint32_t memory_gold(struct config c,unsigned phase,unsigned byte,int *strict) {
  *strict=1;
  uint32_t value=original(byte);
  for(unsigned i=0;i<8;++i) for(unsigned f=0;f<8;++f) {
    if(byte!=field_offset(c,i,f) || !active(c,i)) continue;
    if(phase==1) {
      if(c.store && i<c.start) value=input(f,i);
      // Accessible fields of the faulting segment may or may not have committed.
      else if(c.store && i==c.start && byte<4096) *strict=0;
    } else {
      if(c.store) value=input(f,i);
      if(c.start<8 && i<c.start) value^=0x5b;
    }
  }
  return value;
}
