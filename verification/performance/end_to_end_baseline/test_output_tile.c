#include "software/akv/experimental/quantized_kv/output_tile/kernel.h"
#include <fenv.h>
#include <stdio.h>
#include <stdlib.h>

enum { STRIDE=273, GUARD=8, EXTENT=8*STRIDE+2*GUARD, SOURCE_STRIDE=288 };
extern const unsigned char real_q4_value[], real_q8_value[];
static unsigned cases, real_cases, invalid, unaligned;
static float actual[EXTENT], reference[EXTENT], oracle[EXTENT];
static unsigned char source[32*SOURCE_STRIDE], before[sizeof(source)];
static akv_output_tile_coefficients_t coeff;
#define CHECK(x) do { if (!(x)) { printf("OUTPUT_TILE_FAIL line=%d case=%u\n", __LINE__, cases); exit(1); } } while (0)

static float from_bits(uint32_t bits) { float f; memcpy(&f,&bits,4); return f; }
static float from_half(uint16_t bits) {
  uint32_t sign=(uint32_t)(bits & 0x8000u)<<16;
  unsigned exponent=(bits>>10)&31u, mantissa=bits&1023u;
  if (!exponent) {
    if (!mantissa) return from_bits(sign);
    unsigned shift=0;
    while (!(mantissa&1024u)) { mantissa<<=1; ++shift; }
    return from_bits(sign | ((127u-14u-shift)<<23) | ((mantissa&1023u)<<13));
  }
  return from_bits(sign | ((exponent+112u)<<23) | (mantissa<<13));
}
static void reset(unsigned sticky) {
  CHECK(fesetround(FE_TONEAREST)==0);
  CHECK(feclearexcept(FE_ALL_EXCEPT)==0);
  if (sticky) CHECK(feraiseexcept(FE_DIVBYZERO)==0);
  __asm__ volatile("csrwi vcsr,5; csrwi vstart,0" ::: "memory");
}
static unsigned flags(void) { uintptr_t f; __asm__ volatile("frcsr %0":"=r"(f)); return f; }
static unsigned vector_flags(void) { uintptr_t f; __asm__ volatile("csrr %0,vcsr":"=r"(f)); return f; }

static void one(unsigned heads, unsigned dim, unsigned tokens, unsigned pattern,
                unsigned sticky, const unsigned char *real) {
  static const uint16_t scales[]={0,0x8000,1,0x8001,0x3ff,0x400,0x3c00,0xbc00,0x3555,0x7bff};
  memset(source,0xa5,sizeof(source));
  for (unsigned t=0;t<tokens;++t) {
    for (unsigned b=0;b<dim/32;++b) {
      uint16_t h=scales[(t+b+pattern)%10];
      memcpy(source+t*SOURCE_STRIDE+b*34,&h,2);
      for (unsigned d=0;d<32;++d)
        source[t*SOURCE_STRIDE+b*34+2+d]=(unsigned char)(t*19+b*37+d*47);
    }
    if (real) memcpy(source+t*SOURCE_STRIDE,real+t*136,136);
    coeff.rescale[t]=pattern==0 ? 0 : pattern==1 ? (1u<<heads)-1 :
                     ((t%3==0 ? 0x55u : 0xaau)&((1u<<heads)-1));
    for (unsigned h=0;h<heads;++h) {
      coeff.ms[h][t]=(coeff.rescale[t]&(1u<<h)) ?
          (t%5==0 ? 0.0f : 0.125f*(1+(h+t)%6)) : from_bits(0x7f800001);
      coeff.vs[h][t]=t%7==0 ? -0.0f : 0.0625f*(1+(t+h)%13);
    }
  }
  memcpy(before,source,sizeof(source));
  for (unsigned i=0;i<EXTENT;++i) actual[i]=from_bits(0x4a55aa55);
  for (unsigned h=0;h<heads;++h) for (unsigned d=0;d<dim;++d)
    actual[GUARD+h*STRIDE+d]=pattern==3 ? FLT_MIN : (float)((int)d-64)*0.03125f;
  memcpy(reference,actual,sizeof(actual)); memcpy(oracle,actual,sizeof(actual));
  reset(sticky);
  for (unsigned t=0;t<tokens;++t) {
    float ms[8],vs[8];
    for (unsigned h=0;h<heads;++h) { ms[h]=coeff.ms[h][t]; vs[h]=coeff.vs[h][t]; }
    CHECK(quant_register_pv_update(heads,dim,STRIDE,reference+GUARD,
          source+t*SOURCE_STRIDE,ms,vs,coeff.rescale[t])==AKV_GROUPED_PV_OK);
  }
  const unsigned expected=flags();
  reset(sticky);
  for (unsigned t=0;t<tokens;++t) for (unsigned h=0;h<heads;++h)
    for (unsigned d=0;d<dim;++d) {
      uint16_t half; const unsigned char *block=source+t*SOURCE_STRIDE+d/32*34;
      memcpy(&half,block,2);
      const float v=from_half(half)*(float)(int8_t)block[2+d%32];
      float y=oracle[GUARD+h*STRIDE+d];
      if (coeff.rescale[t]&(1u<<h)) { volatile float scaled=y*coeff.ms[h][t]; y=scaled; }
      oracle[GUARD+h*STRIDE+d]=fmaf(coeff.vs[h][t],v,y);
    }
  CHECK(flags()==expected && memcmp(reference,oracle,sizeof(oracle))==0);
  reset(sticky);
  CHECK(akv_output_tile_update(heads,dim,STRIDE,actual+GUARD,source,SOURCE_STRIDE,
                              sizeof(source),tokens,&coeff)==AKV_GROUPED_PV_OK);
  CHECK(flags()==expected && vector_flags()==5);
  CHECK(memcmp(actual,reference,sizeof(actual))==0 && memcmp(source,before,sizeof(source))==0);
  ++cases; if (real) ++real_cases;
}

static void guards(void) {
  float saved[EXTENT];
  memset(actual,0x5a,sizeof(actual)); memcpy(saved,actual,sizeof(saved));
  memset(&coeff,0,sizeof(coeff));
  for (unsigned i=0;i<15;++i) {
    unsigned h=2,d=128,t=32; size_t stride=STRIDE, ts=SOURCE_STRIDE, bytes=sizeof(source);
    float *y=actual; const void *s=source;
    const akv_output_tile_coefficients_t *c=&coeff;
    reset(1); coeff.rescale[31]=0;
    switch(i) {
      case 0:h=0;break; case 1:h=9;break; case 2:d=31;break;
      case 3:d=257;break; case 4:t=0;break; case 5:t=33;break;
      case 6:stride=SIZE_MAX;break; case 7:ts=135;break;
      case 8:bytes=135;break; case 9:s=y;break; case 10:c=NULL;break;
      case 11:coeff.rescale[31]=4;break; case 12:y=NULL;break;
      case 13:__asm__ volatile("csrwi frm,1":::"memory");break;
      case 14:__asm__ volatile("csrwi vstart,1":::"memory");break;
    }
    const unsigned expected=flags();
    CHECK(akv_output_tile_update(h,d,stride,y,s,ts,bytes,t,c)==AKV_GROUPED_PV_BAD_ARGUMENT);
    CHECK(flags()==expected && vector_flags()==5);
    uintptr_t start; __asm__ volatile("csrr %0,vstart; csrwi vstart,0":"=r"(start)::"memory");
    CHECK(start==(i==14 ? 1u : 0u));
    CHECK(memcmp(actual,saved,sizeof(actual))==0);
    ++invalid;
  }
}

static void byte_alignment(void) {
  /* The last real-data trial supplies 17 finite rows and coefficients.
   * Q8_0 is a byte payload: unlike FP32 output it need not be word-aligned. */
  static unsigned char shifted[sizeof(source)+4];
  for (unsigned offset=1;offset<=3;++offset) {
    memcpy(shifted+offset,source,sizeof(source));
    memset(actual,0,sizeof(actual)); memset(reference,0,sizeof(reference));
    reset(1);
    CHECK(akv_output_tile_update(2,128,STRIDE,reference+GUARD,source,SOURCE_STRIDE,
                                sizeof(source),17,&coeff)==AKV_GROUPED_PV_OK);
    const unsigned expected=flags();
    reset(1);
    CHECK(akv_output_tile_update(2,128,STRIDE,actual+GUARD,shifted+offset,SOURCE_STRIDE,
                                sizeof(source),17,&coeff)==AKV_GROUPED_PV_OK);
    CHECK(flags()==expected && vector_flags()==5 && memcmp(actual,reference,sizeof(actual))==0);
    ++unaligned;
  }
}

int main(void) {
  uintptr_t vlenb; __asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
  if (vlenb!=128) {
    reset(1); memset(actual,0x5a,sizeof(actual)); memcpy(reference,actual,sizeof(actual));
    CHECK(akv_output_tile_update(2,128,STRIDE,actual,source,SOURCE_STRIDE,
                                sizeof(source),1,&coeff)==AKV_GROUPED_PV_BAD_ARGUMENT);
    CHECK(flags()==8 && vector_flags()==5 && memcmp(actual,reference,sizeof(actual))==0);
    puts("OUTPUT_TILE_UNSUPPORTED_PASS no_effects=1"); return 0;
  }
  const unsigned heads[]={1,2,3,4,6,8}, dims[]={32,64,96,128,160,256}, sizes[]={1,2,17,31,32};
  for (unsigned h=0;h<6;++h) for (unsigned d=0;d<6;++d)
    for (unsigned t=0;t<5;++t) for (unsigned p=0;p<4;++p) for (unsigned s=0;s<2;++s)
      one(heads[h],dims[d],sizes[t],p,s,NULL);
  for (unsigned kind=0;kind<2;++kind) for (unsigned head=0;head<8;++head)
    for (unsigned offset=0;offset<2;++offset)
      one(2,128,offset?17:32,2,1,(kind?real_q8_value:real_q4_value)+(head*256+offset*32)*136);
  byte_alignment(); guards();
  printf("OUTPUT_TILE_PASS cases=%u real=%u rejected=%u unaligned=%u exact=1 flags=1 scalar_oracle=1\n",cases,real_cases,invalid,unaligned);
  return 0;
}
