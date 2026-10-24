/* Host ABI/address/schedule spies, NOT quantized GGML arithmetic or RVV proof. */
#include "verification/akv/quantized_kv/shared_rvv_qk.h"
#include <assert.h>
#include <fenv.h>
#include <stdio.h>

static unsigned char keys[2*128*272], queries[8*288];
static shared_rvv_qk_context_t *active;
static unsigned spy_calls, values, visits[8][128];
static unsigned direct, direct_head, direct_token, direct_heads, direct_tokens;
static float *direct_scores;
static size_t direct_stride;

static float score_at(unsigned head, unsigned token, unsigned kv) {
  return ((int)((head*7+token*13+kv*11)%29)-14)*0.03125f;
}
static float value_at(unsigned token, unsigned d) {
  return ((int)((token*17+d*5)%31)-15)*0.0625f;
}
static void dot_spy(int dim, float *out, size_t bs, const void *k,
    size_t bx, const void *q, size_t by, int nrc) {
  assert(dim == (int)active->dim && bs == 0 && bx == 0 && by == 0 && nrc == 1);
  const size_t qo = (const unsigned char *)q-(const unsigned char *)active->query;
  const size_t ko = (const unsigned char *)k-(const unsigned char *)active->key;
  assert(qo%active->query_stride == 0);
  const unsigned head = (unsigned)(qo/active->query_stride);
  assert(head < active->heads && ko >= active->selectedkv*active->head_stride);
  const size_t offset = ko-active->selectedkv*active->head_stride;
  assert(offset%active->token_stride == 0);
  const unsigned token = (unsigned)(offset/active->token_stride);
  assert(token < active->tokens);
  unsigned qmark, kmark;
  memcpy(&qmark,q,sizeof(qmark)); memcpy(&kmark,k,sizeof(kmark));
  assert(qmark == head+1000 && kmark == active->selectedkv*1000+token);
  if (direct) {
    const unsigned h = spy_calls/direct_tokens, t = spy_calls%direct_tokens;
    assert(h < direct_heads && head == direct_head+h && token == direct_token+t);
    assert(out == direct_scores+h*direct_stride+t);
  }
  ++spy_calls; ++visits[head][token];
  *out = score_at(head,token,(unsigned)active->selectedkv);
}
static int value_spy(void *opaque, unsigned token, float *out, unsigned dim) {
  assert(opaque == active && token < active->tokens && dim == active->dim);
  ++values;
  for (unsigned d=0; d<dim; ++d) out[d]=value_at(token,d);
  return 0;
}
static void scale(int dim, float *out, float x) {
  for (int d=0; d<dim; ++d) out[d]*=x;
}
static void mad(int dim, float *out, const float *v, float x) {
  for (int d=0; d<dim; ++d) out[d]=fmaf(v[d],x,out[d]);
}
static shared_rvv_qk_context_t setup(unsigned dim, unsigned heads,
    unsigned tokens, unsigned q4, unsigned interleaved, unsigned kv) {
  const size_t row=(size_t)dim/32*(q4 ? 18 : 34);
  shared_rvv_qk_context_t c={
    .key=keys,.query=queries,.key_bytes=sizeof(keys),.query_bytes=sizeof(queries),
    .token_stride=interleaved ? 2*row : row,
    .head_stride=interleaved ? row : tokens*row,.selectedkv=kv,
    .query_stride=(size_t)dim/32*34+16,.key_row_bytes=row,
    .query_row_bytes=(size_t)dim/32*34,.dim=dim,.heads=heads,.tokens=tokens,
    .kv_heads=2,.dot=dot_spy};
  memset(keys,0x5a,sizeof(keys)); memset(queries,0xc3,sizeof(queries));
  for (unsigned h=0; h<2; ++h)
    for (unsigned t=0; t<tokens; ++t) {
      const unsigned mark=h*1000+t;
      memcpy(keys+h*c.head_stride+t*c.token_stride,&mark,sizeof(mark));
    }
  for (unsigned h=0; h<heads; ++h) {
    const unsigned mark=1000+h;
    memcpy(queries+h*c.query_stride,&mark,sizeof(mark));
  }
  return c;
}
static void reset_spy(shared_rvv_qk_context_t *c) {
  active=c; spy_calls=values=0; memset(visits,0,sizeof(visits));
}
static void coordinate_cases(void) {
  for (unsigned q4=0; q4<2; ++q4)
    for (unsigned layout=0; layout<2; ++layout)
      for (unsigned kv=0; kv<2; ++kv) {
        shared_rvv_qk_context_t c=setup(128,8,128,q4,layout,kv);
        float scores[8*39], expected[8*39];
        const unsigned sizes[]={1,5,7,31,32};
        for (unsigned i=0; i<5; ++i) {
          memset(scores,0xa5,sizeof(scores)); memcpy(expected,scores,sizeof(scores));
          direct=1; direct_head=2; direct_token=128-sizes[i];
          direct_heads=3; direct_tokens=sizes[i];
          direct_scores=scores+2; direct_stride=39;
          reset_spy(&c);
          const uint64_t old_calls=c.callbacks, old_dots=c.dots;
          assert(shared_rvv_qk(&c,2,3,direct_token,sizes[i],scores+2,39)==0);
          for (unsigned h=0; h<3; ++h)
            for (unsigned t=0; t<sizes[i]; ++t)
              expected[2+h*39+t]=score_at(2+h,direct_token+t,kv);
          assert(memcmp(scores,expected,sizeof(scores))==0);
          assert(c.callbacks==old_calls+1 && c.dots==old_dots+3*sizes[i]);
          assert(spy_calls==3*sizes[i]);
        }
      }
  direct=0;
}
static unsigned schedule_cases(void) {
  const unsigned dims[]={32,128,256}, hs[]={1,3,6,8}, ts[]={1,5,32,33,65,128};
  unsigned cases=0;
  for (unsigned q4=0; q4<2; ++q4)
    for (unsigned layout=0; layout<2; ++layout)
      for (unsigned kv=0; kv<2; ++kv)
        for (unsigned di=0; di<3; ++di)
          for (unsigned hi=0; hi<4; ++hi)
            for (unsigned ti=0; ti<6; ++ti) {
              shared_rvv_qk_context_t a=setup(dims[di],hs[hi],ts[ti],q4,layout,kv), b=a;
              unsigned char saved_keys[sizeof(keys)], saved_queries[sizeof(queries)];
              memcpy(saved_keys,keys,sizeof(keys)); memcpy(saved_queries,queries,sizeof(queries));
              float out[8*264], ref[8*264];
              akv_quant_online_workspace_t w;
              memset(out,0xa5,sizeof(out)); memset(ref,0xa5,sizeof(ref));
              akv_quant_online_plan_t p={a.heads,a.dim,a.tokens,0.5f,&a,
                  shared_rvv_qk,value_spy,scale,mad};
              reset_spy(&a); feclearexcept(FE_ALL_EXCEPT); feraiseexcept(FE_DIVBYZERO);
              assert(akv_quant_online_head_major(&p,ref,264,&w)==0);
              const int flags=fetestexcept(FE_ALL_EXCEPT);
              assert(a.callbacks==a.heads*a.tokens && a.dots==a.heads*a.tokens);
              assert(spy_calls==a.dots && values==a.dots);
              for (unsigned h=0; h<a.heads; ++h)
                for (unsigned t=0; t<a.tokens; ++t) assert(visits[h][t]==1);
              p.context=&b; reset_spy(&b);
              feclearexcept(FE_ALL_EXCEPT); feraiseexcept(FE_DIVBYZERO);
              assert(akv_quant_online_shared(&p,out,264,&w)==0);
              assert(flags==fetestexcept(FE_ALL_EXCEPT) && memcmp(out,ref,sizeof(out))==0);
              const unsigned groups=b.heads/4+(b.heads%4)/2+b.heads%2;
              assert(b.callbacks==groups*((b.tokens+31)/32));
              assert(b.dots==b.heads*b.tokens && spy_calls==b.dots && values==b.tokens);
              for (unsigned h=0; h<b.heads; ++h)
                for (unsigned t=0; t<b.tokens; ++t) assert(visits[h][t]==1);
              for (unsigned h=0; h<8; ++h)
                for (unsigned d=0; d<264; ++d) {
                  if (h>=b.heads || d>=b.dim) {
                    uint32_t bits; memcpy(&bits,&out[h*264+d],4);
                    assert(bits==UINT32_C(0xa5a5a5a5));
                  } else assert(isfinite(out[h*264+d]));
                }
              assert(!memcmp(keys,saved_keys,sizeof(keys)) && !memcmp(queries,saved_queries,sizeof(queries)));
              ++cases;
            }
  return cases;
}
static unsigned invalid_cases(void) {
  const shared_rvv_qk_context_t valid=setup(128,6,128,0,1,1);
  float scores[8*32], saved[8*32];
  unsigned count=0;
  for (unsigned i=0; i<42; ++i) {
    shared_rvv_qk_context_t c=valid;
    unsigned h=0, nh=4, t=0, nt=32; size_t stride=32;
    float *s=scores; void *opaque=&c;
    memset(scores,0xa5,sizeof(scores)); memcpy(saved,scores,sizeof(saved));
    switch (i) {
      case 0: opaque=NULL; break;
      case 1: c.dot=NULL; break;
      case 2: c.dim=0; break;
      case 3: c.dim=257; break;
      case 4: c.dim=127; break;
      case 5: c.heads=0; break;
      case 6: c.heads=9; break;
      case 7: c.tokens=0; break;
      case 8: c.tokens=65537; break;
      case 9: c.kv_heads=0; break;
      case 10: c.selectedkv=2; break;
      case 11: nh=0; break;
      case 12: h=UINT32_MAX; break;
      case 13: h=3; break;
      case 14: nt=0; break;
      case 15: nt=33; break;
      case 16: t=UINT32_MAX; break;
      case 17: t=127; break;
      case 18: stride=31; break;
      case 19: stride=SIZE_MAX; break;
      case 20: c.query_row_bytes=135; break;
      case 21: c.key_row_bytes=137; break;
      case 22: c.token_stride=135; break;
      case 23: c.head_stride=135; break;
      case 24: c.query_stride=135; break;
      case 25: c.token_stride=SIZE_MAX; break;
      case 26: c.head_stride=SIZE_MAX; break;
      case 27: c.query_stride=SIZE_MAX; break;
      case 28: c.key_bytes=1; break;
      case 29: c.query_bytes=1; break;
      case 30: c.key=NULL; break;
      case 31: c.query=NULL; break;
      case 32: s=NULL; break;
      case 33: c.callbacks=UINT64_MAX; break;
      case 34: c.dots=UINT64_MAX-127; break;
      case 35: s=(float *)((unsigned char *)scores+1); break;
      case 36: c.key=(const void *)(UINTPTR_MAX-3); break;
      case 37: c.query=(const void *)(UINTPTR_MAX-3); break;
      case 38: s=(float *)(UINTPTR_MAX-3); break;
      case 39: stride=SIZE_MAX/sizeof(float); break;
      case 40: c.key_bytes=(c.kv_heads-1)*c.head_stride+
          (c.tokens-1)*c.token_stride+c.key_row_bytes-1; break;
      case 41: c.query_bytes=(c.heads-1)*c.query_stride+c.query_row_bytes-1; break;
    }
    const shared_rvv_qk_context_t before=c;
    reset_spy(&c); feclearexcept(FE_ALL_EXCEPT);
    assert(shared_rvv_qk(opaque,h,nh,t,nt,s,stride)==AKV_QUANT_BAD_ARGUMENT);
    assert(!fetestexcept(FE_ALL_EXCEPT));
    assert(!memcmp(scores,saved,sizeof(scores)) && !memcmp(&c,&before,sizeof(c)));
    assert(spy_calls==0); ++count;
  }
  /* Destination overlap must also reject before counters or input bytes change. */
  for (unsigned i=0; i<3; ++i) {
    shared_rvv_qk_context_t c=valid, before=c;
    unsigned char k[sizeof(keys)], q[sizeof(queries)];
    memcpy(k,keys,sizeof(keys)); memcpy(q,queries,sizeof(queries)); reset_spy(&c);
    float *s=i==0 ? (float *)keys : i==1 ? (float *)queries : (float *)&c;
    assert(shared_rvv_qk(&c,0,1,0,1,s,32)==AKV_QUANT_BAD_ARGUMENT);
    assert(!memcmp(&c,&before,sizeof(c)) && !memcmp(k,keys,sizeof(k)) && !memcmp(q,queries,sizeof(q)));
    assert(spy_calls==0); ++count;
  }
  return count;
}
int main(void) {
  assert(fesetround(FE_TONEAREST)==0);
  coordinate_cases();
  const unsigned schedules=schedule_cases(), invalid=invalid_cases();
  printf("SHARED_RVV_QK_HOST_PASS coordinates=40 schedules=%u invalid=%u nrc1=1 guards=1 exact=1 flags=1 native=0\n",
      schedules,invalid);
  return 0;
}
