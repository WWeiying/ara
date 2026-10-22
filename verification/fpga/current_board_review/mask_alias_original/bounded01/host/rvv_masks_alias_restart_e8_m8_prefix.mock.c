// Host-only model. Never linked into the architectural SoC/Spike ELF.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifndef CAP
#error CAP required
#endif
#ifndef SEW
#error SEW required
#endif
static unsigned calls,policy,injection,injected;
extern int ma_original_main(void);
unsigned long capacity(void) { return CAP; }
long replay_write(long n,long fd,long p,long count) {
  if(n!=64 || fd!=1 || count<0) abort();
  return (long)fwrite((const void *)p,1,(size_t)count,stdout);
}
static unsigned bit(const void *p,unsigned i) { return (((const uint8_t *)p)[i/8]>>(i%8))&1; }
static void put(void *p,unsigned i,unsigned v) {
  uint8_t *b=p; b[i/8]=(uint8_t)((b[i/8]&~(1u<<(i%8)))|(v<<(i%8)));
}
static unsigned logic(unsigned op,unsigned a,unsigned b) {
  // Four-bit truth tables indexed by (a,b), independent of the original if-chain.
  static const unsigned table[]={8,7,4,6,14,1,13,9};
  return (table[op%8]>>(2*a+b))&1;
}
static uint64_t hash_bytes(uint64_t h,const void *data,unsigned n) {
  const uint8_t *b=data;
  for(unsigned i=0;i<n;++i) h=(h^b[i])*UINT64_C(1099511628211);
  return h;
}
static unsigned long model(unsigned op,const void *a,const void *b,void *out,
                           unsigned long vl,unsigned long cap,const void *mask,unsigned long start) {
  if(cap!=CAP || vl>cap) abort();
  for(unsigned i=0;i<1024;++i)
    if(((const uint64_t *)out)[i]!=UINT64_C(0x5b5b5b5b5b5b5b5b)) abort();
  uint64_t h=hash_bytes(UINT64_C(14695981039346656037),a,cap*SEW/8);
  h=hash_bytes(h,b,cap*SEW/8); h=hash_bytes(h,mask,128);
  if(!injection) printf("CALL %u %u %lu %lu %016llx\n",calls,op,vl,start,(unsigned long long)h);
  for(unsigned i=0;i<cap;++i) {
    unsigned old=bit(op<8 ? a:b,i),result=logic(op,bit(a,i),bit(b,i));
    unsigned value=old;
    if(i>=start && i<vl) value=result;
    else if(start<vl && i>=vl) value=policy==1 ? 1:policy==2 ? result:old;
    put(out,i,value);
  }
  ++calls;
  if(!injected && op==0) {
    if(injection==1 && start<vl) { put(out,start,!bit(out,start)); injected=1; }
    if(injection==2 && start>0 && start<vl) { put(out,0,!bit(out,0)); injected=1; }
    if(injection==3 && start>=vl) { put(out,0,!bit(out,0)); injected=1; }
    if(injection==4 && start<vl) for(unsigned i=vl;i<cap;++i)
      if(bit(a,i) && logic(op,bit(a,i),bit(b,i))) { put(out,i,0); injected=1; break; }
    if(injection==5) { ((uint64_t *)out)[-1]^=1; injected=1; }
    if(injection==6) { injected=1; return 1; }
  }
  return 0;
}
#define OP(n) unsigned long op_##n(const void *a,const void *b,void *o,unsigned long v,unsigned long c,const void *m,unsigned long s) { return model(n,a,b,o,v,c,m,s); }
OP(0) OP(1) OP(2) OP(3) OP(4) OP(5) OP(6) OP(7)
OP(8) OP(9) OP(10) OP(11) OP(12) OP(13) OP(14) OP(15)
int main(int argc,char **argv) {
  policy=argc>1 ? (unsigned)strtoul(argv[1],0,0):0;
  injection=argc>2 ? (unsigned)strtoul(argv[2],0,0):0;
  if(policy>2 || injection>6) return 99;
  int result=ma_original_main();
  printf("HOST_END calls=%u injected=%u result=%d\n",calls,injected,result);
  if(calls!=66 || (injection && injected!=1)) return 98;
  return result;
}
