#define main unused_decode_online_main
#include "test_online.c"
#undef main
#include "prefill_prefix_candidate.h"
#include "software/akv/experimental/quantized_kv/prefill/prefix_schedule.h"

int main(void) {
  uintptr_t vlenb;__asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
  context_t a={0},b={0};
  quant_register_pv_view_t view={raw,RAW_STRIDE,sizeof(raw)};
  if(vlenb!=128) {
    unsigned visible[]={1,2};
    akv_quant_online_plan_t p={2,128,2,0.125f,&b,qk,value,scale,mad};
    memset(actual,0x5a,sizeof(actual));memcpy(expected,actual,sizeof(actual));reset(1);
    CHECK(quant_register_prefill_prefix(&p,visible,actual+8,STRIDE,
              &candidate_workspace,&view)==AKV_QUANT_BAD_ARGUMENT);
    CHECK(!b.qk && !b.value && csr()==8 && !memcmp(actual,expected,sizeof(actual)));
    puts("REGISTER_PREFIX_UNSUPPORTED_VLEN_PASS no_effects=1");return 0;
  }
  for(unsigned t=0;t<MAX_TOKENS;++t) for(unsigned block=0;block<8;++block) {
    uint16_t half=block%2?0xb800:0x3400;
    memcpy(raw+t*RAW_STRIDE+block*34,&half,2);
    for(unsigned d=0;d<32;++d) raw[t*RAW_STRIDE+block*34+2+d]=(unsigned char)(t*17+block*31+d*7);
  }
  const unsigned lengths[]={1,2,20,31,32,33,65};
  for(unsigned heads=1;heads<=8;++heads) for(unsigned dim=32;dim<=256;dim+=32)
    for(unsigned n=0;n<7;++n) for(unsigned pattern=0;pattern<2;++pattern)
      for(unsigned sticky=0;sticky<2;++sticky) {
        unsigned visible[8];
        for(unsigned h=0;h<heads;++h)
          visible[h]=pattern && heads>1?1+(lengths[n]-1)*h/(heads-1):lengths[n];
        a=(context_t){0};b=(context_t){0};
        akv_quant_online_plan_t p={heads,dim,lengths[n],0.125f,&a,qk,value,scale,mad};
        memset(expected,0x5a,sizeof(expected));memcpy(actual,expected,sizeof(actual));
        reset(sticky);
        CHECK(quant_prefill_prefix_schedule(&p,visible,expected+8,STRIDE,&reference_workspace)==0);
        const unsigned flags=csr();
        if(!pattern) {
          memcpy(oracle,actual,sizeof(oracle));reset(sticky);
          scalar_oracle(heads,dim,lengths[n]);
          CHECK(csr()==flags && !memcmp(oracle,expected,sizeof(oracle)));
        }
        p.context=&b;reset(sticky);
        CHECK(quant_register_prefill_prefix(&p,visible,actual+8,STRIDE,&candidate_workspace,&view)==0);
        CHECK(csr()==flags && !memcmp(actual,expected,sizeof(actual)));
        CHECK(a.qk==b.qk && a.value==lengths[n] && !b.value);
        CHECK(!memcmp(reference_workspace.maximum,candidate_workspace.maximum,heads*4));
        CHECK(!memcmp(reference_workspace.sum,candidate_workspace.sum,heads*4));
        ++cases;
      }
  a=(context_t){0};
  akv_quant_online_plan_t p={2,128,2,0.125f,&a,qk,value,scale,mad};
  unsigned bad[]={2,1};
  memset(actual,0x5a,sizeof(actual));memcpy(expected,actual,sizeof(actual));reset(1);
  CHECK(quant_register_prefill_prefix(&p,bad,actual+8,STRIDE,&candidate_workspace,&view)==AKV_QUANT_BAD_ARGUMENT);
  CHECK(!a.qk && !a.value && csr()==8 && !memcmp(actual,expected,sizeof(actual)));
  bad[0]=1;bad[1]=2;a.fail=1;
  CHECK(quant_register_prefill_prefix(&p,bad,actual+8,STRIDE,&candidate_workspace,&view)==AKV_QUANT_QK_FAILED);
  CHECK(a.qk==1 && !a.value);
  printf("REGISTER_PREFIX_PASS cases=%u exact=1 flags=1 guards=1 qk_equal=1 causal=1\n",cases);
  return 0;
}
