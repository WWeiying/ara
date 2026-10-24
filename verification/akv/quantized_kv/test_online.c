#include "software/akv/experimental/quantized_kv/online.h"
#include <assert.h>
#include <fenv.h>
#include <stdio.h>

typedef struct {
  unsigned heads, tokens, dim, qk_calls, value_calls;
  unsigned fail_qk, fail_value;
} fixture_t;

static float score_at(unsigned head, unsigned token) {
  return ((int)((head*7 + token*13) % 29) - 14) * 0.03125f;
}
static float value_at(unsigned token, unsigned dim) {
  return ((int)((token*17 + dim*5) % 31) - 15) * 0.0625f;
}
static int qk(void *opaque, unsigned first_head, unsigned heads,
    unsigned first_token, unsigned tokens, float *scores, size_t stride) {
  fixture_t *f = opaque;
  if (++f->qk_calls == f->fail_qk) return 1;
  assert(heads == 1 || heads == 2 || heads == 4);
  assert(first_head + heads <= f->heads && first_token + tokens <= f->tokens);
  assert(tokens > 0 && tokens <= 32 && stride == 32);
  for (unsigned h = 0; h < heads; ++h)
    for (unsigned t = 0; t < tokens; ++t)
      scores[h*stride+t] = score_at(first_head+h, first_token+t);
  return 0;
}
static int value(void *opaque, unsigned token, float *output, unsigned dim) {
  fixture_t *f = opaque;
  if (++f->value_calls == f->fail_value) return 1;
  assert(token < f->tokens && dim == f->dim);
  for (unsigned d = 0; d < dim; ++d) output[d] = value_at(token,d);
  return 0;
}
static void scale(int dim, float *output, float factor) {
  for (int d = 0; d < dim; ++d) output[d] *= factor;
}
static void mad(int dim, float *output, const float *v, float weight) {
  for (int d = 0; d < dim; ++d) output[d] = fmaf(v[d],weight,output[d]);
}
static uint32_t bits(float x) {
  uint32_t result;
  memcpy(&result,&x,4);
  return result;
}

int main(void) {
  const unsigned dims[] = {32,64,96,128,256}, tokens[] = {1,31,32,33,63,64,65,128};
  unsigned cases = 0;
  for (unsigned di = 0; di < 5; ++di)
    for (unsigned heads = 1; heads <= 8; ++heads)
      for (unsigned ti = 0; ti < 8; ++ti) {
        fixture_t baseline = {.heads=heads,.tokens=tokens[ti],.dim=dims[di]}, shared = baseline;
        akv_quant_online_plan_t p = {heads,dims[di],tokens[ti],0.5f,&baseline,qk,value,scale,mad};
        float a[8*264], b[8*264];
        akv_quant_online_workspace_t wa,wb;
        memset(a,0xa5,sizeof(a)); memset(b,0xa5,sizeof(b));
        memset(&wa,0xa5,sizeof(wa)); memset(&wb,0xa5,sizeof(wb));
        feclearexcept(FE_ALL_EXCEPT);
        assert(akv_quant_online_head_major(&p,a,264,&wa) == AKV_QUANT_OK);
        const int flags_a = fetestexcept(FE_ALL_EXCEPT);
        p.context = &shared;
        feclearexcept(FE_ALL_EXCEPT);
        assert(akv_quant_online_shared(&p,b,264,&wb) == AKV_QUANT_OK);
        const int flags_b = fetestexcept(FE_ALL_EXCEPT);
        assert(flags_a == flags_b && memcmp(a,b,sizeof(a)) == 0);
        unsigned groups = heads/4 + (heads%4)/2 + heads%2;
        assert(baseline.qk_calls == heads*p.tokens && baseline.value_calls == heads*p.tokens);
        assert(shared.qk_calls == groups*((p.tokens+31)/32) && shared.value_calls == p.tokens);
        for (unsigned head = 0; head < 8; ++head)
          for (unsigned d = 0; d < 264; ++d) {
            if (head >= heads || d >= p.dim) {
              assert(bits(a[head*264+d]) == UINT32_C(0xa5a5a5a5));
              continue;
            }
            /* Independent full softmax in double, not the online recurrence. */
            double sum = 0.0, numerator = 0.0;
            for (unsigned token = 0; token < p.tokens; ++token) {
              const double probability = exp((double)score_at(head,token)*0.5);
              sum += probability;
              numerator += probability*(double)value_at(token,d);
            }
            assert(fabs((double)a[head*264+d] - numerator/sum) < 0.00001);
          }
        ++cases;
      }
  fixture_t f = {.heads=3,.tokens=33,.dim=64};
  akv_quant_online_plan_t p = {3,64,33,0.5f,&f,qk,value,scale,mad};
  akv_quant_online_workspace_t w;
  float output[3*64];
  memset(output,0xa5,sizeof(output));
  assert(akv_quant_online_shared(&p,output,SIZE_MAX,&w) == AKV_QUANT_BAD_ARGUMENT);
  p.heads = 9;
  assert(akv_quant_online_shared(&p,output,64,&w) == AKV_QUANT_BAD_ARGUMENT);
  p.heads = 3;
  const uint32_t snan = UINT32_C(0x7f800001);
  memcpy(&p.score_scale,&snan,4);
  feclearexcept(FE_ALL_EXCEPT);
  assert(akv_quant_online_shared(&p,output,64,&w) == AKV_QUANT_BAD_ARGUMENT);
  assert(!fetestexcept(FE_INVALID));
  assert(f.qk_calls == 0 && f.value_calls == 0);
  for (unsigned i = 0; i < 3*64; ++i) assert(bits(output[i]) == UINT32_C(0xa5a5a5a5));
  p.score_scale = 0.5f;
  f.fail_qk = 2;
  assert(akv_quant_online_shared(&p,output,64,&w) == AKV_QUANT_QK_FAILED);
  assert(f.qk_calls == 2 && f.value_calls == 0);
  f.qk_calls = f.value_calls = f.fail_qk = 0;
  f.fail_value = 2;
  assert(akv_quant_online_shared(&p,output,64,&w) == AKV_QUANT_VALUE_FAILED);
  assert(f.value_calls == 2);
  printf("QUANT_ONLINE_HOST_PASS cases=%u exact_order=1 double_oracle=1 callback_work=1 guards=1 errors=0\n",cases);
  return 0;
}
