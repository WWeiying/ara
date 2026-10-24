#include "software/akv/experimental/paired_heads/f32_pv/runtime.h"
#include <assert.h>
#include <stdio.h>

static float score[8*64],output[8*128],scale[8];
static unsigned cursor,heads,dim,tokens,calls;
static int enabled;

static void call(const float *s,float *o,const float *a,unsigned t,unsigned h,unsigned d,int paired) {
  assert(s == score+cursor*64 && o == output+cursor*dim && a == scale+cursor);
  assert(t == tokens && d == dim && cursor+h <= heads);
  assert(paired == (enabled && cursor+1 < heads));
  assert(h == (paired ? 2u : enabled ? 1u : heads));
  cursor += h;
  ++calls;
}

void akv_v2_update_outputs_f32_generic(const float *s,float *o,const float *a,
                                     uint32_t t,uint32_t h,uint32_t d) {
  call(s,o,a,t,h,d,0);
}
void akv_experimental_pv_f32_pair(const float *s,float *o,const float *a,uint32_t t,uint32_t d) {
  call(s,o,a,t,2,d,1);
}

int main(void) {
  unsigned schedules = 0;
  const unsigned dims[] = {64,96,128};
  akv_capabilities_t c = {.valid=1,.enabled=1,.f16_payload=1,.context_count=1,.max_q_rows=8,
      .token_axis_valid=1,.token_axis_enabled=1,.token_axis_tail=1,.token_axis_row_view=1,
      .token_axis_tile_tokens=64,.head_dim_64=1,.head_dim_128=1,.token_axis_d_axis_tail=1};
  /* PANEL4 is intentionally absent: V-row delivery does not require it. */
  assert(c.token_axis_column_panel4 == 0);
  for (unsigned d = 0; d < 3; ++d) {
    dim = dims[d];
    for (heads = 1; heads <= 8; ++heads) {
      const int expected = heads >= 2 && !(heads == 6 && dim == 128);
      assert(akv_prefill_pair_pv_capable(1,128,&c,heads,dim) == expected);
      assert(!akv_prefill_pair_pv_capable(0,128,&c,heads,dim));
      assert(!akv_prefill_pair_pv_capable(2,128,&c,heads,dim));
      assert(!akv_prefill_pair_pv_capable(1,16,&c,heads,dim));
      assert(!akv_prefill_pair_pv_capable(1,128,NULL,heads,dim));
#define MISSING(field) do { akv_capabilities_t bad = c; bad.field = 0; \
        assert(!akv_prefill_pair_pv_capable(1,128,&bad,heads,dim)); } while (0)
      MISSING(valid); MISSING(enabled); MISSING(f16_payload); MISSING(context_count);
      MISSING(max_q_rows); MISSING(token_axis_valid); MISSING(token_axis_enabled);
      MISSING(token_axis_tail); MISSING(token_axis_row_view); MISSING(token_axis_tile_tokens);
#undef MISSING
      akv_capabilities_t bad_dim = c;
      if (dim == 64) bad_dim.head_dim_64 = 0;
      else if (dim == 96) bad_dim.token_axis_d_axis_tail = 0;
      else bad_dim.head_dim_128 = 0;
      assert(!akv_prefill_pair_pv_capable(1,128,&bad_dim,heads,dim));
      for (tokens = 1; tokens <= 64; ++tokens)
        for (enabled = 0; enabled <= 1; ++enabled) {
          cursor = calls = 0;
          akv_prefill_pair_pv_dispatch(enabled,score,output,scale,tokens,heads,dim);
          assert(cursor == heads && calls == (enabled ? (heads+1)/2 : 1));
          ++schedules;
        }
    }
  }
  assert(!akv_prefill_pair_pv_capable(1,128,&c,2,256));
  assert(!akv_prefill_pair_pv_capable(1,128,&c,9,64));
  printf("F32_PAIR_RUNTIME_HOST_PASS schedules=%u native_execution=0\n",schedules);
  return 0;
}
