#include "software/akv/experimental/quantized_kv/output_tile/online.h"
#include <fenv.h>
#include <stdio.h>
#include <stdlib.h>

enum { STRIDE=269, EXTENT=8*STRIDE+16, GUARD=8, TS=288, NT=129 };
extern const unsigned char real_q4_value[], real_q8_value[];
static float result[3][EXTENT];
static akv_quant_online_workspace_t work[3];
static unsigned char values[NT*TS];
static unsigned cases, real_cases, rejected, failures;
static unsigned calls, fail_at, value_calls, mad_calls, scale_calls, pattern;
static unsigned trace[128][4];
static quant_register_pv_view_t active_view;
#define CHECK(x) do { if (!(x)) { printf("OUTPUT_ONLINE_FAIL line=%d case=%u\n",__LINE__,cases); exit(1); } } while (0)

static float from_bits(uint32_t b) { float f; memcpy(&f,&b,4); return f; }
static float half(uint16_t b) {
  const uint32_t sign=(uint32_t)(b&0x8000u)<<16;
  unsigned e=(b>>10)&31u,m=b&1023u;
  if (!e) {
    if (!m) return from_bits(sign);
    unsigned shift=0;
    while (!(m&1024u)) { m<<=1; ++shift; }
    return from_bits(sign|((127u-14u-shift)<<23)|((m&1023u)<<13));
  }
  return from_bits(sign|((e+112u)<<23)|(m<<13));
}
static void reset(void) {
  CHECK(fesetround(FE_TONEAREST)==0 && feclearexcept(FE_ALL_EXCEPT)==0);
  CHECK(feraiseexcept(FE_DIVBYZERO)==0);
  __asm__ volatile("csrwi vcsr,5; csrwi vstart,0":::"memory");
  calls=value_calls=mad_calls=scale_calls=0;
  memset(trace,0,sizeof(trace));
}
static unsigned flags(void) { uintptr_t f; __asm__ volatile("frcsr %0":"=r"(f)); return f; }
static unsigned vflags(void) { uintptr_t f; __asm__ volatile("csrr %0,vcsr":"=r"(f)); return f; }
static float score(unsigned h,unsigned t) {
  switch(pattern) {
    case 0:return (float)((int)t-64)*0.125f+(float)h*0.03125f;
    case 1:return (float)(64-(int)t)*0.125f;
    case 2:return t%32==0 ? 40.0f : -40.0f;
    default:return (float)((int)((t*37+h*13)%31)-15)*0.125f;
  }
}
static int qk(void *ctx,unsigned head,unsigned heads,unsigned first,unsigned tokens,
              float *out,size_t stride) {
  (void)ctx;
  CHECK(calls<128);
  unsigned *entry=trace[calls++];
  entry[0]=head; entry[1]=heads; entry[2]=first; entry[3]=tokens;
  if (calls==fail_at) return 1;
  for (unsigned h=0;h<heads;++h) for (unsigned t=0;t<tokens;++t)
    out[h*stride+t]=score(head+h,first+t);
  return 0;
}
static int value(void *ctx,unsigned token,float *out,unsigned dim) {
  (void)ctx; ++value_calls;
  for (unsigned d=0;d<dim;++d) {
    const unsigned char *b=active_view.data+token*active_view.token_stride+d/32*34;
    uint16_t h; memcpy(&h,b,2);
    out[d]=half(h)*(float)(int8_t)b[2+d%32];
  }
  return 0;
}
static void scale(int dim,float *y,float s) {
  ++scale_calls;
  for (int i=0;i<dim;++i) y[i]*=s;
}
static void mad(int dim,float *y,const float *v,float s) {
  ++mad_calls;
  for (int i=0;i<dim;++i) y[i]=fmaf(s,v[i],y[i]);
}
static akv_quant_online_plan_t plan(unsigned heads,unsigned dim,unsigned tokens) {
  return (akv_quant_online_plan_t){heads,dim,tokens,0.125f,NULL,qk,value,scale,mad};
}
static void initialize(void) {
  for (unsigned i=0;i<EXTENT;++i) result[0][i]=from_bits(0x4a55aa55);
  memcpy(result[1],result[0],sizeof(result[0]));
  memcpy(result[2],result[0],sizeof(result[0]));
  memset(work,0x5a,sizeof(work));
}
static void one(unsigned heads,unsigned dim,unsigned tokens,unsigned mode,
                const unsigned char *real) {
  pattern=mode; fail_at=0;
  static const uint16_t scales[]={0,0x8000,1,0x3ff,0x400,0x3555,0xbc00,0x7bff};
  memset(values,0xa5,sizeof(values));
  for (unsigned t=0;t<tokens;++t) {
    for (unsigned b=0;b<dim/32;++b) {
      const uint16_t h=scales[(t+b)%8];
      memcpy(values+t*TS+b*34,&h,2);
      for (unsigned d=0;d<32;++d) values[t*TS+b*34+2+d]=(unsigned char)(t*19+d*47+b*37);
    }
    if (real) memcpy(values+t*TS,real+t*136,136);
  }
  quant_register_pv_view_t view={values,TS,sizeof(values)};
  active_view=view;
  akv_quant_online_plan_t p=plan(heads,dim,tokens);
  initialize(); reset();
  CHECK(akv_quant_online_shared(&p,result[0]+GUARD,STRIDE,&work[0])==AKV_QUANT_OK);
  const unsigned expected_flags=flags(), expected_calls=calls;
  CHECK(value_calls==tokens && mad_calls==heads*tokens);
  unsigned expected_trace[128][4]; memcpy(expected_trace,trace,sizeof(trace));
  for (unsigned impl=1;impl<3;++impl) {
    reset();
    const int status=impl==1 ? quant_register_online(&p,result[impl]+GUARD,STRIDE,&work[impl],&view) :
                            akv_output_tile_online(&p,result[impl]+GUARD,STRIDE,&work[impl],&view);
    CHECK(status==AKV_QUANT_OK && flags()==expected_flags && vflags()==5);
    CHECK(calls==expected_calls && memcmp(trace,expected_trace,sizeof(trace))==0);
    CHECK(value_calls==0 && mad_calls==0 && scale_calls==heads);
    CHECK(memcmp(result[0],result[impl],sizeof(result[0]))==0);
    CHECK(memcmp(work[0].maximum,work[impl].maximum,heads*sizeof(float))==0);
    CHECK(memcmp(work[0].sum,work[impl].sum,heads*sizeof(float))==0);
  }
  ++cases; if (real) ++real_cases;
}
static void failure_tests(void) {
  akv_quant_online_plan_t p=plan(8,128,65);
  quant_register_pv_view_t view={values,TS,sizeof(values)};
  active_view=view; pattern=3;
  for (fail_at=1;fail_at<=6;++fail_at) {
    initialize(); reset();
    CHECK(quant_register_online(&p,result[1]+GUARD,STRIDE,&work[1],&view)==AKV_QUANT_QK_FAILED);
    const unsigned expected=flags();
    reset();
    CHECK(akv_output_tile_online(&p,result[2]+GUARD,STRIDE,&work[2],&view)==AKV_QUANT_QK_FAILED);
    CHECK(calls==fail_at && value_calls==0 && mad_calls==0 && scale_calls==0);
    CHECK(flags()==expected && memcmp(result[1],result[2],sizeof(result[1]))==0);
    CHECK(memcmp(work[1].sum,work[2].sum,sizeof(work[1].sum))==0);
    CHECK(memcmp(work[1].maximum,work[2].maximum,sizeof(work[1].maximum))==0);
    ++failures;
  }
  fail_at=0;
}
static void guards(int unsupported) {
  const unsigned count=unsupported ? 1 : 17;
  for (unsigned i=0;i<count;++i) {
    akv_quant_online_plan_t p=plan(2,128,65);
    quant_register_pv_view_t view={values,TS,sizeof(values)};
    float *out=result[2]+GUARD; size_t stride=STRIDE;
    initialize(); reset();
    if (!unsupported) switch(i) {
      case 0:p.heads=0;break; case 1:p.heads=9;break;
      case 2:p.dim=31;break; case 3:p.dim=288;break;
      case 4:p.tokens=0;break; case 5:p.tokens=65537;break;
      case 6:stride=SIZE_MAX;break; case 7:view.bytes=135;break;
      case 8:view.token_stride=135;break; case 9:view.data=(const void*)out;break;
      case 10:view.data=(const void*)&work[2];break;
      case 11:p.qk=NULL;break; case 12:p.score_scale=NAN;break;
      case 13:out=(float*)((char*)out+1);break;
      case 14:view.token_stride=SIZE_MAX;break;
      case 15:__asm__ volatile("csrwi frm,1":::"memory");break;
      case 16:__asm__ volatile("csrwi vstart,1":::"memory");break;
    }
    const unsigned expected=flags();
    CHECK(akv_output_tile_online(&p,out,stride,&work[2],&view)==AKV_QUANT_BAD_ARGUMENT);
    CHECK(flags()==expected && vflags()==5 && calls==0 && value_calls==0 && scale_calls==0);
    uintptr_t start; __asm__ volatile("csrr %0,vstart; csrwi vstart,0":"=r"(start)::"memory");
    CHECK(start==(!unsupported && i==16 ? 1u : 0u));
    CHECK(memcmp(result[2],result[0],sizeof(result[2]))==0);
    CHECK(memcmp(&work[2],&work[0],sizeof(work[2]))==0);
    ++rejected;
  }
}
int main(void) {
  uintptr_t vlenb; __asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
  if (vlenb!=128) { guards(1); puts("OUTPUT_ONLINE_UNSUPPORTED_PASS no_effects=1"); return 0; }
  const unsigned heads[]={1,2,3,4,6,8}, dims[]={32,96,128,160,256};
  const unsigned tokens[]={1,31,32,33,65,129};
  for (unsigned h=0;h<6;++h) for (unsigned d=0;d<5;++d)
    for (unsigned t=0;t<6;++t) for (unsigned p=0;p<4;++p)
      one(heads[h],dims[d],tokens[t],p,NULL);
  for (unsigned kind=0;kind<2;++kind) for (unsigned kv=0;kv<8;++kv)
    for (unsigned size=0;size<2;++size)
      one(2,128,size?129:65,3,(kind?real_q8_value:real_q4_value)+kv*256*136);
  failure_tests(); guards(0);
  printf("OUTPUT_ONLINE_PASS cases=%u real=%u rejected=%u callback_failures=%u exact=1 flags=1\n",
         cases,real_cases,rejected,failures);
  return 0;
}
