#define main decode_fixture_main
#include "verification/akv/quantized_kv/test_native.c"
#undef main
#include "admission_aligned.h"
#include "admission_baseline.h"
#include <fenv.h>

static int compare_admission(const quant_prefill_input_t *p,quant_prefill_admission_t *out) {
  quant_prefill_admission_t a,b;memset(&a,0xa5,sizeof(a));memset(&b,0xa5,sizeof(b));
  fenv_t before;assert(!fegetenv(&before));
  int old=quant_prefill_admit_baseline(p,&a),flags=fetestexcept(FE_ALL_EXCEPT);
  assert(!fesetenv(&before));
  int now=quant_prefill_admit(p,&b);
  assert(old==now && flags==fetestexcept(FE_ALL_EXCEPT) && !memcmp(&a,&b,sizeof(a)));
  if(now==AKV_QUANT_SELECT_OK)*out=b;
  return now;
}

static float multi_query[8][4][128];
static float multi_output[4][8][136];
static uint16_t multi_mask[4][68];
static const unsigned prefixes[]={33,65,1,32};

static quant_prefill_input_t fixture(void) {
  assert(qbs_device_init_reference(1024,&device)==QBS_STATUS_OK);
  akv_quant_selection_input_t p=prepare(128,8,1,65,1);
  for(unsigned h=0;h<8;++h) for(unsigned row=0;row<4;++row)
    for(unsigned d=0;d<128;++d) multi_query[h][row][d]=(int)((d+h+row)%7)-3;
  memset(multi_output,0xa5,sizeof(multi_output));
  for(unsigned row=0;row<4;++row) for(unsigned t=0;t<68;++t)
    multi_mask[row][t]=t<prefixes[row]?0:0xfc00;
  p.query=(akv_quant_tensor_view_t){multi_query,sizeof(multi_query),512,2048,128,4,8};
  p.output=(akv_quant_tensor_view_t){multi_output,sizeof(multi_output),8*136*4,136*4,128,4,8};
  p.mask=&multi_mask[0][0];p.mask_bytes=sizeof(multi_mask);
  return (quant_prefill_input_t){p,sizeof(multi_mask[0])};
}
static void unchanged_output(void) {
  for(size_t i=0;i<sizeof(multi_output);++i) assert(((unsigned char *)multi_output)[i]==0xa5);
}
int main(void) {
  quant_prefill_input_t p=fixture();
  quant_prefill_admission_t result;
  assert(compare_admission(&p,&result)==AKV_QUANT_SELECT_OK);
  assert(result.queries==4 && result.common.visible_tokens==65 && result.common.group_heads==8);
  assert(!memcmp(result.visible,prefixes,sizeof(prefixes)));unchanged_output();
  unsigned cases=1;
  for(unsigned bad=0;bad<18;++bad) {
    p=fixture();
    int expected=AKV_QUANT_SELECT_LAYOUT;
    switch(bad) {
      case 0: p.tensors.requested=0;expected=AKV_QUANT_SELECT_DISABLED;break;
      case 1: p.tensors.query.tokens=257;expected=AKV_QUANT_SELECT_SHAPE;break;
      case 2: p.tensors.output.tokens=3;expected=AKV_QUANT_SELECT_SHAPE;break;
      case 3: p.tensors.query.bytes=sizeof(multi_query)-1;break;
      case 4: p.mask_row_stride=1;expected=AKV_QUANT_SELECT_MASK;break;
      case 5: p.tensors.mask_bytes=3*sizeof(multi_mask[0]);expected=AKV_QUANT_SELECT_MASK;break;
      case 6: multi_mask[3][33]=0;expected=AKV_QUANT_SELECT_MASK;break;
      case 7: multi_mask[2][0]=0xfc00;expected=AKV_QUANT_SELECT_MASK;break;
      case 8: p.tensors.output.data=multi_query;p.tensors.output.bytes=sizeof(multi_query);
              p.tensors.output.token_stride=512;p.tensors.output.head_stride=2048;
              expected=AKV_QUANT_SELECT_ALIAS;break;
      case 9: { uint32_t snan=0x7f800001;memcpy(&multi_query[7][3][127],&snan,4);
                expected=AKV_QUANT_SELECT_NONFINITE;break; }
      case 10: for(unsigned d=0;d<32;++d) { uint32_t tiny=1;memcpy(&multi_query[7][0][d],&tiny,4); }
               expected=AKV_QUANT_SELECT_QUERY_RANGE;break;
      case 11: { uint16_t nan=0x7c01;memcpy(keys+64*72,&nan,2);
                 expected=AKV_QUANT_SELECT_NONFINITE;break; }
      case 12: { uint16_t nan=0x7c01;memcpy(values+64*136,&nan,2);
                 expected=AKV_QUANT_SELECT_NONFINITE;break; }
      case 13: p.tensors.device=NULL;expected=AKV_QUANT_SELECT_CAPABILITY;break;
      case 14: device.capabilities.activation_alignment_log2=3;
               expected=AKV_QUANT_SELECT_CAPABILITY;break;
      case 15: p.tensors.frm=1;expected=AKV_QUANT_SELECT_CAPABILITY;break;
      case 16: p.tensors.query.heads=p.tensors.output.heads=2;device.capabilities.max_m=2;
               expected=AKV_QUANT_SELECT_CAPABILITY;break;
      case 17: p.tensors.query.heads=p.tensors.output.heads=2;device.capabilities.max_results=64;
               expected=AKV_QUANT_SELECT_CAPABILITY;break;
    }
    quant_prefill_admission_t before;memset(&result,0xa5,sizeof(result));before=result;
    feclearexcept(FE_ALL_EXCEPT);feraiseexcept(FE_DIVBYZERO);
    assert(compare_admission(&p,&result)==expected);
    assert(fetestexcept(FE_ALL_EXCEPT)==FE_DIVBYZERO && !memcmp(&result,&before,sizeof(result)));
    unchanged_output();++cases;
  }
  // Hidden KV rows must not affect admission of the visible union.
  p=fixture();for(unsigned row=0;row<4;++row) for(unsigned t=33;t<65;++t) multi_mask[row][t]=0xfc00;
  uint16_t nan=0x7c01;memcpy(keys+64*72,&nan,2);memcpy(values+64*136,&nan,2);
  assert(compare_admission(&p,&result)==AKV_QUANT_SELECT_OK && result.common.visible_tokens==33);
  unchanged_output();++cases;
  p=fixture();p.tensors.query.data=(const char *)p.tensors.query.data+1;
  assert(compare_admission(&p,&result)==AKV_QUANT_SELECT_LAYOUT);
  p=fixture();p.tensors.query.token_stride+=2;
  assert(compare_admission(&p,&result)==AKV_QUANT_SELECT_LAYOUT);
  p=fixture();p.tensors.mask=(const uint16_t *)((const char *)p.tensors.mask+1);
  assert(compare_admission(&p,&result)==AKV_QUANT_SELECT_MASK);
  printf("PREFILL_ALIGNED_ADMISSION_PASS cases=%u all_query_rows=1 union_kv=1 no_output_writes=1 rejection_plan_unchanged=1\n",cases);
}
