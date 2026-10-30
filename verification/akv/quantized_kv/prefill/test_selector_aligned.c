#define main selector_fixture_main
#include "verification/akv/quantized_kv/test_native.c"
#undef main
#include "selector_baseline.h"
#include "software/akv/experimental/quantized_kv/selection_strided.h"
#include <fenv.h>

static unsigned char padded_keys[2*65*138] __attribute__((aligned(64)));
static unsigned compared,rejected;

static int compare(const akv_quant_selection_input_t *p) {
  akv_quant_selection_t a,b,poison;memset(&poison,0xa5,sizeof(poison));
  memcpy(&a,&poison,sizeof(a));memcpy(&b,&poison,sizeof(b));
  feclearexcept(FE_ALL_EXCEPT);feraiseexcept(FE_DIVBYZERO);
  int old=akv_quant_select_strided_baseline(p,&a),flags=fetestexcept(FE_ALL_EXCEPT);
  feclearexcept(FE_ALL_EXCEPT);feraiseexcept(FE_DIVBYZERO);
  int now=akv_quant_select_strided(p,&b);
  assert(old==now && flags==FE_DIVBYZERO && fetestexcept(FE_ALL_EXCEPT)==flags);
  if(now==AKV_QUANT_SELECT_OK) {
    assert(a.group_heads==b.group_heads && a.kv_heads==b.kv_heads && a.dim==b.dim &&
      a.visible_tokens==b.visible_tokens && a.key_profile==b.key_profile &&
      a.key_row_bytes==b.key_row_bytes && a.query_quant_row_bytes==b.query_quant_row_bytes);
  } else {
    assert(!memcmp(&a,&poison,sizeof(a)) && !memcmp(&b,&poison,sizeof(b)));++rejected;
  }
  ++compared;return now;
}

int main(void) {
  assert(qbs_device_init_reference(1024,&device)==QBS_STATUS_OK);
  unsigned dims[]={32,96,128},prefix[]={1,31,32,33,65};
  for(unsigned di=0;di<3;++di)for(unsigned g=1;g<=8;++g)for(unsigned h=1;h<=2;++h)
    for(unsigned q4=0;q4<2;++q4)for(unsigned pi=0;pi<5;++pi) {
      akv_quant_selection_input_t p=prepare(dims[di],g,h,prefix[pi],q4);
      assert(compare(&p)==AKV_QUANT_SELECT_OK);
      size_t row=(dims[di]/32)*(q4?18:34),stride=row+2;
      memset(padded_keys,0xa5,sizeof(padded_keys));
      for(unsigned head=0;head<h;++head)for(unsigned t=0;t<65;++t)
        memcpy(padded_keys+(head*65+t)*stride,keys+(head*65+t)*row,row);
      p.key.data=padded_keys;p.key.bytes=sizeof(padded_keys);
      p.key.token_stride=stride;p.key.head_stride=65*stride;
      assert(compare(&p)==AKV_QUANT_SELECT_OK);
    }
  for(unsigned bad=0;bad<12;++bad) {
    assert(qbs_device_init_reference(1024,&device)==QBS_STATUS_OK);
    akv_quant_selection_input_t p=prepare(128,6,2,33,1);
    switch(bad) {
      case 0:p.query.data=(const char *)p.query.data+1;break;
      case 1:p.query.head_stride+=2;break;
      case 2:p.key.data=(const char *)p.key.data+1;break;
      case 3:p.value.token_stride+=1;break;
      case 4:{uint32_t nan=0x7f800001;memcpy(query,&nan,4);break;}
      case 5:{uint16_t nan=0x7c01;memcpy(keys,&nan,2);break;}
      case 6:{uint16_t nan=0x7c01;memcpy(values,&nan,2);break;}
      case 7:p.mask=(const uint16_t *)((const char *)p.mask+1);break;
      case 8:p.output.data=p.query.data;break;
      case 9:p.frm=1;break;
      case 10:p.key.bytes=1;break;
      case 11:p.device=NULL;break;
    }
    assert(compare(&p)!=AKV_QUANT_SELECT_OK);
  }
  assert(compared==972 && rejected==12);
  puts("SELECTOR_ALIGNED_PASS cases=972 rejected=12 flags_equal=1 failed_plan_unchanged=1");
  return 0;
}
