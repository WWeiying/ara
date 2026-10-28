#define main native_fixture_main
#include "verification/akv/quantized_kv/test_native.c"
#undef main
#include "selector_block_max.h"
#include <fenv.h>

static unsigned cases;
static int compare(const akv_quant_selection_input_t *p) {
  akv_quant_selection_t a,b,poison;memset(&poison,0xa5,sizeof(poison));
  memcpy(&a,&poison,sizeof(a));memcpy(&b,&poison,sizeof(b));
  feclearexcept(FE_ALL_EXCEPT);feraiseexcept(FE_DIVBYZERO);
  int before=akv_quant_select_strided(p,&a);int flags=fetestexcept(FE_ALL_EXCEPT);
  feclearexcept(FE_ALL_EXCEPT);feraiseexcept(FE_DIVBYZERO);
  int after=akv_quant_select_strided_block_max(p,&b);
  assert(before==after && flags==FE_DIVBYZERO && fetestexcept(FE_ALL_EXCEPT)==flags);
  if(after==AKV_QUANT_SELECT_OK) {
    assert(a.group_heads==b.group_heads && a.kv_heads==b.kv_heads && a.dim==b.dim &&
      a.visible_tokens==b.visible_tokens && a.key_profile==b.key_profile &&
      a.key_row_bytes==b.key_row_bytes && a.query_quant_row_bytes==b.query_quant_row_bytes);
  } else assert(!memcmp(&a,&poison,sizeof(a)) && !memcmp(&b,&poison,sizeof(b)));
  ++cases;return after;
}

static void set_bits(unsigned element,uint32_t bits) {memcpy(&query[0][element],&bits,4);}

int main(void) {
  assert(qbs_device_init_reference(1024,&device)==QBS_STATUS_OK);
  unsigned dims[]={32,96,128},prefixes[]={1,31,32,33,65};
  for(unsigned d=0;d<3;++d)for(unsigned g=1;g<=8;++g)for(unsigned h=1;h<=2;++h)
    for(unsigned q4=0;q4<2;++q4)for(unsigned t=0;t<5;++t) {
      akv_quant_selection_input_t p=prepare(dims[d],g,h,prefixes[t],q4);
      assert(compare(&p)==AKV_QUANT_SELECT_OK);
    }
  const uint32_t patterns[]={0,0x80000000,1,0x007fffff,0x00800000,0x037fffff,
    0x03800000,0x03800001,0x3f800000,0x4afde03f,0x4afde040,0x4afde041,
    0x7f7fffff,0x7f800000,0xff800000,0x7fc12345,0x7f800001,0xff800001};
  for(unsigned block=0;block<4;++block)for(unsigned pos=0;pos<32;++pos)
    for(unsigned i=0;i<sizeof(patterns)/sizeof(patterns[0]);++i) {
      akv_quant_selection_input_t p=prepare(128,2,1,33,1);
      memset(query[0],0,sizeof(query[0]));set_bits(block*32+pos,patterns[i]);compare(&p);
    }
  for(unsigned pos=1;pos<32;++pos) {
    akv_quant_selection_input_t p=prepare(128,2,1,33,1);
    memset(query[0],0,sizeof(query[0]));set_bits(0,0x4afde041);set_bits(pos,0x7f800001);
    assert(compare(&p)==AKV_QUANT_SELECT_NONFINITE);
  }
  akv_quant_selection_input_t p=prepare(128,2,1,33,1);
  memset(query[0],0,sizeof(query[0]));set_bits(0,0x4afde041);set_bits(32,0x7f800001);
  assert(compare(&p)==AKV_QUANT_SELECT_QUERY_RANGE);
  set_bits(0,0x7f800001);set_bits(32,0x4afde041);
  assert(compare(&p)==AKV_QUANT_SELECT_NONFINITE);
  memset(query[0],0,sizeof(query[0]));set_bits(0,0x03800000);
  assert(compare(&p)==AKV_QUANT_SELECT_OK);
  set_bits(0,0x037fffff);assert(compare(&p)==AKV_QUANT_SELECT_QUERY_RANGE);
  assert(cases==2819);
  puts("SELECTOR_BLOCK_MAX_PASS cases=2819 flags_equal=1 rejection_priority=1");return 0;
}
