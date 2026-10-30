#include "software/akv/experimental/quantized_kv/online.h"
#include <assert.h>
#include <fenv.h>
#include <stdio.h>

typedef struct {
  unsigned heads, dim, tokens, pattern, qk_calls, value_calls;
  unsigned fail_qk, fail_value;
  uint64_t trace;
} fixture_t;

static unsigned scale_calls, mad_calls;
static void trace(fixture_t *f, unsigned event) {
  f->trace = (f->trace ^ event) * UINT64_C(1099511628211);
}
static float score_at(const fixture_t *f, unsigned h, unsigned t) {
  switch (f->pattern) {
    case 0: return (float)((int)((h*7+t*13)%29)-14)*0.03125f;
    case 1: return (float)t*0.125f;
    case 2: return -(float)t*0.125f;
    case 3: return 0.0f;
    default: return t%2 ? -200.0f : (float)t*0.0625f;
  }
}
static float value_at(unsigned t, unsigned d) {
  if (d%11 == 0) return d%2 ? -0.0f : 0.0f;
  if (d%13 == 0) return 0x1p-140f;
  return (float)((int)((t*17+d*5)%31)-15)*0.0625f;
}
static int qk(void *opaque, unsigned first_head, unsigned heads,
    unsigned first_token, unsigned tokens, float *scores, size_t stride) {
  fixture_t *f = opaque;
  trace(f, 0x10000u + first_head*8192u + heads*1024u + first_token*32u + tokens);
  if (++f->qk_calls == f->fail_qk) return 1;
  assert(first_head+heads <= f->heads && first_token+tokens <= f->tokens);
  for (unsigned h=0; h<heads; ++h)
    for (unsigned t=0; t<tokens; ++t)
      scores[h*stride+t] = score_at(f, first_head+h, first_token+t);
  return 0;
}
static int value(void *opaque, unsigned token, float *output, unsigned dim) {
  fixture_t *f = opaque;
  trace(f, 0x200000u + token);
  if (++f->value_calls == f->fail_value) return 1;
  assert(token < f->tokens && dim == f->dim);
  for (unsigned d=0; d<dim; ++d) output[d] = value_at(token,d);
  return 0;
}
static void scale(int dim, float *output, float factor) {
  ++scale_calls;
  for (int d=0; d<dim; ++d) {
    volatile float rounded = output[d]*factor;
    output[d] = rounded;
  }
}
static void mad(int dim, float *output, const float *v, float weight) {
  ++mad_calls;
  for (int d=0; d<dim; ++d) output[d] = fmaf(v[d],weight,output[d]);
}

static void compare(unsigned heads, unsigned dim, unsigned tokens,
    unsigned pattern, unsigned sticky, unsigned fail_qk, unsigned fail_value) {
  fixture_t a = {.heads=heads,.dim=dim,.tokens=tokens,.pattern=pattern,
                 .fail_qk=fail_qk,.fail_value=fail_value}, b=a;
  akv_quant_online_plan_t p = {heads,dim,tokens,0.5f,&a,qk,value,scale,mad};
  _Alignas(64) float ya[8*264], yb[8*264];
  akv_quant_online_workspace_t wa, wb;
  memset(ya,0xa5,sizeof(ya)); memset(yb,0xa5,sizeof(yb));
  memset(&wa,0xa5,sizeof(wa)); memset(&wb,0xa5,sizeof(wb));
  feclearexcept(FE_ALL_EXCEPT);
  if (sticky) feraiseexcept(FE_DIVBYZERO);
  scale_calls=mad_calls=0;
  const int ra=akv_quant_online_shared(&p,ya,264,&wa);
  const int fa=fetestexcept(FE_ALL_EXCEPT);
  const unsigned old_mad=mad_calls, old_scale=scale_calls;
  p.context=&b;
  feclearexcept(FE_ALL_EXCEPT);
  if (sticky) feraiseexcept(FE_DIVBYZERO);
  scale_calls=mad_calls=0;
  const int rb=akv_quant_online_shared_grouped(&p,yb,264,&wb);
  const int fb=fetestexcept(FE_ALL_EXCEPT);
  assert(ra == rb && fa == fb);
  assert(memcmp(ya,yb,sizeof(ya)) == 0);
  assert(memcmp(wa.maximum,wb.maximum,sizeof(wa.maximum)) == 0);
  assert(memcmp(wa.sum,wb.sum,sizeof(wa.sum)) == 0);
  assert(a.trace == b.trace && a.qk_calls == b.qk_calls && a.value_calls == b.value_calls);
  assert(mad_calls == 0);
  if (ra == AKV_QUANT_OK) {
    assert(scale_calls == heads && old_scale >= heads && old_mad == heads*tokens);
    const unsigned groups=heads/4+(heads%4)/2+heads%2;
    assert(a.qk_calls == groups*((tokens+31)/32) && a.value_calls == tokens);
    for (unsigned h=0; h<heads; ++h) {
      double maximum=-INFINITY;
      for (unsigned t=0; t<tokens; ++t)
        if (score_at(&a,h,t)*0.5 > maximum) maximum=score_at(&a,h,t)*0.5;
      for (unsigned d=0; d<dim; ++d) {
        double denominator=0, numerator=0;
        for (unsigned t=0; t<tokens; ++t) {
          const double weight=exp(score_at(&a,h,t)*0.5-maximum);
          denominator+=weight; numerator+=weight*value_at(t,d);
        }
        assert(fabs(ya[h*264+d]-numerator/denominator) < 0.00001);
      }
    }
  } else assert(scale_calls == 0);
  for (unsigned h=0; h<8; ++h)
    for (unsigned d=0; d<264; ++d)
      if (h>=heads || d>=dim) {
        uint32_t u;
        memcpy(&u,&ya[h*264+d],4);
        assert(u == UINT32_C(0xa5a5a5a5));
      }
}

int main(void) {
  assert(fesetround(FE_TONEAREST) == 0);
  const unsigned dims[]={32,64,96,128,256};
  const unsigned lengths[]={1,31,32,33,64,65,128};
  unsigned cases=0, errors=0;
  for (unsigned h=1; h<=8; ++h)
    for (unsigned d=0; d<5; ++d)
      for (unsigned t=0; t<7; ++t)
        for (unsigned p=0; p<5; ++p)
          for (unsigned s=0; s<2; ++s) {
            compare(h,dims[d],lengths[t],p,s,0,0); ++cases;
          }
  for (unsigned i=1; i<=6; ++i) {
    compare(6,128,65,0,1,i,0); ++errors;
  }
  const unsigned fail_tokens[]={1,2,32,33,64,65};
  for (unsigned i=0; i<6; ++i) {
    compare(6,128,65,0,1,0,fail_tokens[i]); ++errors;
  }
  fixture_t fixture={.heads=2,.dim=32,.tokens=1};
  akv_quant_online_plan_t p={2,32,1,0.5f,&fixture,qk,value,scale,mad};
  akv_quant_online_workspace_t w;
  _Alignas(64) float output[64], original[64];
  memset(output,0xa5,sizeof(output)); memcpy(original,output,sizeof(output));
  memset(&w,0xa5,sizeof(w));
  akv_quant_online_workspace_t original_w=w;
  const uint32_t snan=UINT32_C(0x7f800001);
  memcpy(&p.score_scale,&snan,4);
  feclearexcept(FE_ALL_EXCEPT);
  assert(akv_quant_online_shared_grouped(&p,output,32,&w) == AKV_QUANT_BAD_ARGUMENT);
  assert(!fetestexcept(FE_INVALID));
  p.score_scale=0.5f;
  assert(akv_quant_online_shared_grouped(&p,output,SIZE_MAX,&w) == AKV_QUANT_BAD_ARGUMENT);
  assert(akv_quant_online_shared_grouped(&p,(float *)((char *)output+1),32,&w) == AKV_QUANT_BAD_ARGUMENT);
  assert(akv_quant_online_shared_grouped(&p,w.value,32,&w) == AKV_QUANT_BAD_ARGUMENT);
  assert(akv_quant_online_shared_grouped(NULL,output,32,&w) == AKV_QUANT_BAD_ARGUMENT);
  assert(akv_quant_online_shared_grouped(&p,output,32,NULL) == AKV_QUANT_BAD_ARGUMENT);
  assert(fixture.qk_calls == 0 && fixture.value_calls == 0);
  assert(memcmp(output,original,sizeof(output)) == 0 && memcmp(&w,&original_w,sizeof(w)) == 0);
  printf("GROUPED_ONLINE_PASS cases=%u injected_errors=%u exact=1 flags=1 callbacks=1 guards=1 double_oracle=1\n",cases,errors);
  return 0;
}
