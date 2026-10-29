#include "online_candidate.h"
#include "software/akv/experimental/quantized_kv/q8_0_value.h"
#include <stdio.h>
#include <stdlib.h>

enum { MAX_TOKENS=65, RAW_STRIDE=280, STRIDE=264, WORDS=8*STRIDE+16 };
static unsigned char raw[MAX_TOKENS*RAW_STRIDE];
static float expected[WORDS],actual[WORDS];
static akv_quant_online_workspace_t reference_workspace,candidate_workspace;
typedef struct { unsigned qk,value; int fail; } context_t;
static unsigned cases;
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"REGISTER_ONLINE_FAIL line=%d case=%u\n",__LINE__,cases);exit(1); } } while (0)
static unsigned csr(void) {
  unsigned long v;__asm__ volatile("frcsr %0":"=r"(v));return (unsigned)v;
}
static void reset(unsigned sticky) {
  __asm__ volatile("fscsr %0"::"r"((unsigned long)(sticky?8:0)):"memory");
}
static int qk(void *opaque,unsigned h,unsigned n,unsigned first,unsigned count,
              float *scores,size_t stride) {
  context_t *c=opaque;++c->qk;
  if(c->fail) return 1;
  for(unsigned a=0;a<n;++a) for(unsigned t=0;t<count;++t)
    scores[a*stride+t]=((int)(((h+a)*7+(first+t)*11)%29)-14)*0.25f;
  return 0;
}
static int value(void *opaque,unsigned token,float *out,unsigned dim) {
  context_t *c=opaque;++c->value;
  akv_quant_q8_0_value(raw+token*RAW_STRIDE,out,dim);return 0;
}
static void scale(int n,float *out,float f) {
  for(int i=0;i<n;++i) { volatile float x=out[i]*f;out[i]=x; }
}
static void mad(int n,float *out,const float *v,float f) {
  for(int i=0;i<n;++i) out[i]=fmaf(v[i],f,out[i]);
}
static void one(unsigned heads,unsigned dim,unsigned tokens,unsigned sticky) {
  context_t a={0},b={0};
  akv_quant_online_plan_t p={heads,dim,tokens,0.125f,&a,qk,value,scale,mad};
  quant_register_pv_view_t view={raw,RAW_STRIDE,sizeof(raw)};
  memset(expected,0x5a,sizeof(expected));memcpy(actual,expected,sizeof(actual));
  reset(sticky);
  CHECK(akv_quant_online_shared(&p,expected+8,STRIDE,&reference_workspace)==0);
  unsigned flags=csr();p.context=&b;reset(sticky);
  CHECK(quant_register_online(&p,actual+8,STRIDE,&candidate_workspace,&view)==0);
  CHECK(csr()==flags && memcmp(actual,expected,sizeof(actual))==0);
  CHECK(a.qk==b.qk && a.value==tokens && b.value==0);
  CHECK(memcmp(reference_workspace.maximum,candidate_workspace.maximum,heads*4)==0);
  CHECK(memcmp(reference_workspace.sum,candidate_workspace.sum,heads*4)==0);
  ++cases;
}
int main(void) {
  static const unsigned lengths[]={1,2,20,31,32,33,65};
  for(unsigned t=0;t<MAX_TOKENS;++t) for(unsigned b=0;b<8;++b) {
    uint16_t half=(b%2)?0xb800:0x3400;
    memcpy(raw+t*RAW_STRIDE+b*34,&half,2);
    for(unsigned d=0;d<32;++d) raw[t*RAW_STRIDE+b*34+2+d]=(unsigned char)(t*17+b*31+d*7);
  }
  for(unsigned h=1;h<=8;++h) for(unsigned d=32;d<=256;d+=32)
    for(unsigned t=0;t<7;++t) for(unsigned sticky=0;sticky<2;++sticky)
      one(h,d,lengths[t],sticky);
  context_t c={0};
  akv_quant_online_plan_t p={2,128,20,0.125f,&c,qk,value,scale,mad};
  quant_register_pv_view_t view={raw,RAW_STRIDE,1};
  memset(actual,0x5a,sizeof(actual));memcpy(expected,actual,sizeof(actual));
  reset(1);
  CHECK(quant_register_online(&p,actual+8,STRIDE,&candidate_workspace,&view)==AKV_QUANT_BAD_ARGUMENT);
  CHECK(c.qk==0 && c.value==0 && csr()==8 && memcmp(actual,expected,sizeof(actual))==0);
  view.bytes=sizeof(raw);c.fail=1;
  CHECK(quant_register_online(&p,actual+8,STRIDE,&candidate_workspace,&view)==AKV_QUANT_QK_FAILED);
  CHECK(c.qk==1 && c.value==0);
  printf("REGISTER_ONLINE_PASS cases=%u exact=1 flags=1 guards=1 terminal_error=1\n",cases);
  return 0;
}
