#include "candidate.h"
#include "software/akv/experimental/quantized_kv/q8_0_value.h"
#include <fenv.h>
#include <stdio.h>
#include <stdlib.h>

enum { STRIDE=273, GUARD=8, COUNT=8*STRIDE+2*GUARD };
extern const unsigned char real_q4_value[],real_q8_value[];
static unsigned cases,invalid;
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"REGISTER_PV_FAIL line=%d case=%u\n",__LINE__,cases);exit(1); } } while (0)
static float from_bits(uint32_t u) { float x;memcpy(&x,&u,4);return x; }
static float from_half(uint16_t h) {
  uint32_t sign=(uint32_t)(h&0x8000u)<<16;
  uint32_t exponent=(h>>10)&31, mantissa=h&1023;
  if (!exponent) {
    if (!mantissa) return from_bits(sign);
    unsigned shift=0;
    while (!(mantissa&1024u)) { mantissa<<=1;++shift; }
    return from_bits(sign|((127-14-shift)<<23)|((mantissa&1023u)<<13));
  }
  return from_bits(sign|((exponent+112)<<23)|(mantissa<<13));
}
static void reset(unsigned sticky) {
  CHECK(fesetround(FE_TONEAREST)==0);
  CHECK(feclearexcept(FE_ALL_EXCEPT)==0);
  if(sticky) CHECK(feraiseexcept(FE_DIVBYZERO)==0);
  __asm__ volatile("csrwi vcsr,5":::"memory");
}
static unsigned flags(void) { unsigned long f;__asm__ volatile("frcsr %0":"=r"(f));return (unsigned)f; }
static unsigned vflags(void) { unsigned long f;__asm__ volatile("csrr %0,vcsr":"=r"(f));return (unsigned)f; }
__attribute__((noinline)) static void reference(unsigned heads,unsigned dim,size_t stride,
    float *y,const float *v,const float *ms,const float *vs,unsigned mask) {
  for(unsigned h=0;h<heads;++h) {
    if(mask&(1u<<h)) for(unsigned d=0;d<dim;++d) {
      volatile float scaled=y[h*stride+d]*ms[h];y[h*stride+d]=scaled;
    }
    for(unsigned d=0;d<dim;++d) y[h*stride+d]=fmaf(v[d],vs[h],y[h*stride+d]);
  }
}
__attribute__((noinline)) int register_pv_probe(unsigned h,unsigned d,size_t stride,
    float *y,const void *v,const float *ms,const float *vs,unsigned mask) {
  return quant_register_pv_update(h,d,stride,y,v,ms,vs,mask);
}
static void one(unsigned heads,unsigned dim,unsigned pad,unsigned pattern,unsigned mask,
                unsigned sticky,const unsigned char *real) {
  float actual[COUNT],expected[COUNT],decoded[256],oracle[COUNT],independent[256];
  float ms[8],vs[8];
  unsigned char bytes[272],before[272];
  const size_t stride=dim+pad;
  static const uint16_t scales[]={0,0x8000,1,0x8001,0x03ff,0x0400,
                                  0x3c00,0xbc00,0x3c01,0x7bff,0xfbff,0x3555};
  static const uint32_t values[]={0,0x80000000,1,0x80000001,0x007fffff,
    0x00800000,0x80800000,0x3f000000,0xbf000000,0x3f800001,0x7f7fffff,0xff7fffff};
  memset(bytes,0xa5,sizeof(bytes));
  for(unsigned b=0;b<dim/32;++b) {
    uint16_t scale=scales[(b+pattern)%12];memcpy(bytes+b*34,&scale,2);
    for(unsigned d=0;d<32;++d) bytes[b*34+2+d]=(unsigned char)((b*32+d)*47+pattern*19);
  }
  if(real) memcpy(bytes,real,dim/32*34);
  memcpy(before,bytes,sizeof(bytes));
  for(unsigned i=0;i<COUNT;++i) actual[i]=from_bits(0x4a55aa55);
  for(unsigned h=0;h<heads;++h) {
    ms[h]=from_bits(values[(pattern+h+7)%12]);vs[h]=from_bits(values[(pattern+2*h+3)%12]);
    if(pattern==1) ms[h]=vs[h]=-0.0f;
    if(pattern==2) { ms[h]=0.1f;vs[h]=0; }
    if(pattern==3) { ms[h]=2;vs[h]=0; }
    if(pattern==4) { ms[h]=(mask&(1u<<h))?0.5f:from_bits(0x7f800001);vs[h]=1; }
    for(unsigned d=0;d<dim;++d) actual[GUARD+h*stride+d]=
      pattern==2?FLT_MIN:pattern==3?FLT_MAX:from_bits(values[(pattern+h+d)%12]);
  }
  memcpy(expected,actual,sizeof(actual));memcpy(oracle,actual,sizeof(actual));
  reset(sticky);
  akv_quant_q8_0_value(bytes,decoded,dim);
  CHECK(flags()==(sticky?8u:0u));
  reference(heads,dim,stride,expected+GUARD,decoded,ms,vs,mask);
  const unsigned reference_flags=flags();
  reset(sticky);
  for(unsigned b=0;b<dim/32;++b) {
    uint16_t h;memcpy(&h,bytes+b*34,2);const float scale=from_half(h);
    for(unsigned d=0;d<32;++d) independent[b*32+d]=scale*(float)(int8_t)bytes[b*34+2+d];
  }
  CHECK(memcmp(independent,decoded,dim*4)==0);
  reference(heads,dim,stride,oracle+GUARD,independent,ms,vs,mask);
  CHECK(flags()==reference_flags && memcmp(expected,oracle,sizeof(expected))==0);
  reset(sticky);
  CHECK(register_pv_probe(heads,dim,stride,actual+GUARD,bytes,ms,vs,mask)==AKV_GROUPED_PV_OK);
  CHECK(flags()==reference_flags && vflags()==5);
  CHECK(memcmp(actual,expected,sizeof(actual))==0);
  CHECK(memcmp(bytes,before,sizeof(bytes))==0);
  ++cases;
}
static void rejected(void) {
  float y[COUNT],copy[COUNT],ms[8]={0},vs[8]={0};unsigned char src[272]={0};
  memset(y,0x5a,sizeof(y));memcpy(copy,y,sizeof(y));
  for(unsigned i=0;i<16;++i) {
    unsigned h=2,d=128,mask=0;size_t stride=136;float *out=y;
    const void *v=src;const float *m=ms,*s=vs;
    switch(i) {
      case 0:h=0;break;case 1:h=9;break;case 2:d=31;break;case 3:d=257;break;
      case 4:d=33;break;case 5:stride=127;break;case 6:mask=4;break;
      case 7:stride=SIZE_MAX;break;case 8:out=NULL;break;case 9:v=NULL;break;
      case 10:m=NULL;break;case 11:s=NULL;break;case 12:v=y;break;
      case 13:m=y+130;break;case 14:s=y+136;break;
      case 15:v=(const void *)(UINTPTR_MAX-1);break;
    }
    reset(1);CHECK(register_pv_probe(h,d,stride,out,v,m,s,mask)==AKV_GROUPED_PV_BAD_ARGUMENT);
    CHECK(flags()==8 && vflags()==5 && memcmp(y,copy,sizeof(y))==0);++invalid;
  }
}
int main(void) {
  uintptr_t vb;__asm__ volatile("csrr %0,vlenb":"=r"(vb));CHECK(vb==128);
  for(unsigned h=1;h<=8;++h) for(unsigned dim=32;dim<=256;dim+=32)
    for(unsigned pad=0;pad<2;++pad) for(unsigned pattern=0;pattern<12;++pattern)
      for(unsigned which=0;which<4;++which) for(unsigned sticky=0;sticky<2;++sticky) {
        const unsigned masks[]={0,(1u<<h)-1,0x55u&((1u<<h)-1),1u<<(h-1)};
        one(h,dim,pad?17:0,pattern,masks[which],sticky,NULL);
      }
  for(unsigned kind=0;kind<2;++kind) for(unsigned head=0;head<8;++head)
    for(unsigned token=0;token<20;++token) for(unsigned heads=2;heads<=8;heads+=6) {
      const unsigned char *v=(kind?real_q8_value:real_q4_value)+(head*256+token)*136;
      one(heads,128,8,token%12,(1u<<heads)-1,token%2,v);
    }
  rejected();
  printf("REGISTER_PV_PASS cases=%u invalid=%u real_cases=640 exact=1 flags=1 guards=1\n",cases,invalid);
  return 0;
}
