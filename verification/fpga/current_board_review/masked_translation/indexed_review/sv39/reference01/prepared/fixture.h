#include <stdint.h>
#define IX_VA UINT64_C(0x40000000)
#define IX_G UINT64_C(0xe370697ce370697c)
#define IX_TM UINT64_C(0x8000031888)
#define IX_DONE UINT64_C(0x6978737633390008)
#ifndef IX_GROUP
#define IX_GROUP 0
#endif
struct config { unsigned unmapped,store,boundary,mode,split,mask,base,start; };
struct snapshot { uint64_t lo[8]; uint32_t v[10][32]; uint64_t hi[8]; };
_Static_assert(sizeof(struct snapshot)==1408,"snapshot ABI");
static struct config config(unsigned t) {
  struct config c;
  c.split=t%2; t/=2; c.mode=t%4; t/=4;
  c.boundary=1+2*(t%3); t/=3; c.store=t%2; c.unmapped=t/2;
  c.mask=c.mode==0 ? 255:c.mode==1 ? 170:c.mode==2 ? 36:0;
  c.base=4096-(c.boundary*7+(c.split ? 3:0))*4;
  c.start=8;
  for(unsigned i=c.boundary;i<8;++i) if((c.mask>>i)&1) { c.start=i; break; }
  return c;
}
static unsigned active(struct config c,unsigned i) { return (c.mask>>i)&1; }
static unsigned index_offset(struct config c,unsigned i) {
  unsigned slot=i<c.boundary ? (i+1)%c.boundary:i==c.boundary ? c.boundary:
    i<8 ? c.boundary+1+(i-c.boundary)%(8-c.boundary-1):i;
  return slot*28;
}
static unsigned field_offset(struct config c,unsigned i,unsigned f) {
  return c.base+index_offset(c,i)+4*f;
}
static uint32_t original(unsigned byte) { return byte/4*37+11; }
static uint32_t input(unsigned f,unsigned i) { return 101+i*13+f*29; }
static uint32_t seed(unsigned r,unsigned i) { return 0x6c700000u^(r<<16)^i; }
static uint32_t vector_gold(struct config c,unsigned phase,unsigned r,unsigned i,int *strict) {
  *strict=1;
  if(r==0) return i<16 ? index_offset(c,i):seed(r,i);
  if(r==1 || r==9 || i>=16) return seed(r,i);
  if(c.store) return input(r-2,i);
  if(i>=8 || !active(c,i)) return 0x5b;
  if(phase==1 && i>=c.start) { *strict=0; return 0; }
  return original(field_offset(c,i,r-2));
}
static inline uint32_t memory_gold(struct config c,unsigned phase,unsigned byte,int *strict) {
  *strict=1;
  uint32_t value=original(byte);
  for(unsigned i=0;i<8;++i) for(unsigned f=0;f<7;++f) {
    if(byte!=field_offset(c,i,f) || !active(c,i)) continue;
    if(phase==1) {
      if(c.store && i<c.start) value=input(f,i);
      // A faulting segment may have completed an implementation-dependent subset.
      else if(c.store && byte<4096) *strict=0;
    } else {
      if(c.store) value=input(f,i);
      if(c.start<8 && i<c.start) value^=0x5b;
    }
  }
  return value;
}
