/* Independent generated expected rows; never linked into either vector ELF. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#if SEW == 8
typedef uint8_t word;
#else
#error This Host fixture is only full original SEW8
#endif
#include "host_rows.h"
static unsigned calls, mutation, injected;
extern int arithmetic_main(void);
unsigned long capacity(void) { return 32; }
long replay_write(long n,long fd,long p,long size) {
  if(n!=64 || fd!=1 || size<0)abort();
  return fwrite((void *)p,1,size,stdout);
}
static uint64_t hash(uint64_t h,const void *p,unsigned size) {
  const uint8_t *b=p;
  for(unsigned i=0;i<size;++i)h=(h^b[i])*UINT64_C(1099511628211);
  return h;
}
static unsigned long model(unsigned op,const word *a,const word *b,word *out,
    unsigned long vl,unsigned long cap,const uint8_t *mask,unsigned long start) {
  if(calls>=COUNT || cap!=32)abort();
  const struct row *r=&expected_rows[calls];
  uint64_t h=hash(UINT64_C(14695981039346656037),a,cap*sizeof(word));
  h=hash(h,b,cap*sizeof(word));h=hash(h,mask,128);h=hash(h,out-1,34*sizeof(word));
  if(r->op!=op || r->vl!=vl || r->start!=start || h!=r->hash)abort();
  for(unsigned i=0;i<32;++i)out[i]=r->out[i];
  ++calls;
  if(!injected) {
    if(mutation>=1 && mutation<=4 && op==0)for(unsigned i=0;i<32;++i) {
      unsigned active=(mask[i/8]>>(i%8))&1;
      unsigned eligible=mutation==1 ? i>=start && i<vl && active :
        mutation==2 ? start>0 && start<vl && i<start :
        mutation==3 ? i>=start && i<vl && !active : start<vl && i>=vl;
      if(eligible){out[i]^=1;injected=1;break;}
    }
    if(mutation==5){out[-1]^=1;injected=1;}
    if(mutation==6){out[cap]^=1;injected=1;}
    if(mutation==7){injected=1;return 1;}
    if(mutation==8){injected=1;return UINT64_C(1)<<32;}
    if(mutation==9 && op==25 && vl && start==0 && (mask[0]&1)){out[0]^=1;injected=1;}
  }
  return 0;
}
#define OP(n) unsigned long op_##n(const word *a,const word *b,word *o,unsigned long v,unsigned long c,const uint8_t *m,unsigned long s) {return model(n,a,b,o,v,c,m,s);}
OP(0) OP(1) OP(2) OP(3) OP(4) OP(5) OP(6) OP(7) OP(8) OP(9)
OP(10) OP(11) OP(12) OP(13) OP(14) OP(15) OP(16) OP(17) OP(18) OP(19)
OP(20) OP(21) OP(22) OP(23) OP(24) OP(25) OP(26) OP(27) OP(28) OP(29)
OP(30) OP(31) OP(32) OP(33) OP(34)
int main(int argc,char **argv) {
  mutation=argc>1 ? strtoul(argv[1],0,0):0;
  int result=arithmetic_main();
  printf("HOST_END calls=%u injected=%u result=%d\n",calls,injected,result);
  if(calls!=COUNT || (mutation && injected!=1))return 98;
  return result;
}
