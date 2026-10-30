#define main decode_fixture_main
#include "verification/akv/quantized_kv/test_native.c"
#undef main
#include "execute.h"

static float qmulti[6][5][96], ymulti[5][6][136], expected[5][6][136];
static uint16_t masks[5][65];
static quant_prefill_workspace_t scratch;
static const unsigned lengths[]={1,33,65,32,20};
static unsigned submitted,fail_on;
static quant_prefill_report_t *fail_after_group;

static qbs_status_t multi_execute(void *opaque,const qbs_descriptor_t *desc,unsigned m,
    const void *activation,float *out,size_t stride,unsigned n,int segmented) {
  (void)opaque;++submitted;
  if((fail_on && submitted==fail_on) ||
      (fail_after_group && fail_after_group->native.completed_groups==1)) return QBS_STATUS_EXECUTION;
  qbs_descriptor_fields_t f=qbs_unpack_descriptor_header(desc->header);
  assert(f.k_blocks==3 && f.n==n && m<=4 && !segmented && !((uintptr_t)activation&3u));
  size_t offset=desc->weight_base-(uintptr_t)keys;
  assert(offset%(3*18)==0 && offset+n*3*18<=sizeof(keys));
  float packed[128];qbs_ref_result_t report;
  assert(qbs_ref_execute(desc,m,8,1024,(uintptr_t)activation,(void *)(uintptr_t)desc->weight_base,
      n*3*18,activation,m*3*34,packed,128,NULL,NULL,&report)==QBS_REF_OK);
  for(unsigned row=0;row<m;++row) memcpy(out+row*stride,packed+row*32,n*4);
  return QBS_STATUS_OK;
}

int main(void) {
  assert(qbs_device_init_reference(1024,&device)==QBS_STATUS_OK);
  akv_quant_selection_input_t p=prepare(96,3,2,65,1);
  for(unsigned h=0;h<6;++h) for(unsigned q=0;q<5;++q) for(unsigned d=0;d<96;++d)
    qmulti[h][q][d]=(int)((h+q+d)%7)-3;
  for(unsigned q=0;q<5;++q) for(unsigned t=0;t<65;++t) masks[q][t]=t<lengths[q]?0:0xfc00;
  memset(ymulti,0xa5,sizeof(ymulti));memset(expected,0xa5,sizeof(expected));
  p.query=(akv_quant_tensor_view_t){qmulti,sizeof(qmulti),96*4,5*96*4,96,5,6};
  p.output=(akv_quant_tensor_view_t){ymulti,sizeof(ymulti),6*136*4,136*4,96,5,6};
  p.mask=&masks[0][0];p.mask_bytes=sizeof(masks);
  quant_prefill_input_t request={p,sizeof(masks[0])};
  executor_t old={0};
  akv_quant_native_bindings_t bindings={quantize,decode,scale,mad,execute,&old};
  for(unsigned q=0;q<5;++q) {
    akv_quant_selection_input_t one=p;
    one.query.data=(unsigned char *)p.query.data+q*p.query.token_stride;
    one.query.bytes-=q*p.query.token_stride;one.query.tokens=1;
    one.output.data=expected[q];one.output.bytes=sizeof(expected[q]);one.output.tokens=1;
    one.mask=masks[q];one.mask_bytes=sizeof(masks[q]);old.input=&one;
    akv_quant_native_report_t report;
    assert(akv_quant_native_execute(&one,&bindings,&workspace,sizeof(workspace),&report)==AKV_QUANT_NATIVE_OK);
  }
  bindings.execute=multi_execute;bindings.executor_context=NULL;
  quant_prefill_report_t report;
  assert(quant_prefill_execute(&request,&bindings,&scratch,sizeof(scratch),&report)==AKV_QUANT_NATIVE_OK);
  assert(!memcmp(ymulti,expected,sizeof(expected)) && report.queries_quantized==30 &&
    report.native.completed_groups==4 && report.native.value_decodes==260 &&
    report.native.command_attempts==submitted && report.key_panels==0 && report.alignment_copies>0);
  // Invalid last query must reject the entire operation before any callback.
  float saved=qmulti[5][4][95];
  uint32_t nan=0x7f800001;memcpy(&qmulti[5][4][95],&nan,4);
  memset(ymulti,0xa5,sizeof(ymulti));submitted=quant_calls=decode_calls=0;
  assert(quant_prefill_execute(&request,&bindings,&scratch,sizeof(scratch),&report)==AKV_QUANT_NATIVE_FALLBACK);
  assert(!submitted && !quant_calls && !decode_calls);
  for(size_t i=0;i<sizeof(ymulti);++i) assert(((unsigned char *)ymulti)[i]==0xa5);
  qmulti[5][4][95]=saved;
  // Workspace alias and short allocations also reject before callbacks.
  request.tensors.output.data=&scratch;request.tensors.output.bytes=sizeof(scratch);
  assert(quant_prefill_execute(&request,&bindings,&scratch,sizeof(scratch),&report)==AKV_QUANT_NATIVE_FALLBACK &&
         report.native.selection_reason==AKV_QUANT_SELECT_ALIAS && !submitted);
  request.tensors.output=p.output;
  assert(quant_prefill_execute(&request,&bindings,&scratch,sizeof(scratch)-1,&report)==AKV_QUANT_NATIVE_FALLBACK && !submitted);
  fail_on=1;
  assert(quant_prefill_execute(&request,&bindings,&scratch,sizeof(scratch),&report)==AKV_QUANT_NATIVE_EXECUTION_FAILED &&
         submitted==1 && report.native.completed_groups==0);
  for(size_t i=0;i<sizeof(ymulti);++i) assert(((unsigned char *)ymulti)[i]==0xa5);
  fail_on=0;submitted=0;fail_after_group=&report;
  assert(quant_prefill_execute(&request,&bindings,&scratch,sizeof(scratch),&report)==AKV_QUANT_NATIVE_EXECUTION_FAILED &&
         report.native.completed_groups==1);
  for(unsigned q=0;q<5;++q) for(unsigned h=0;h<6;++h) for(unsigned d=0;d<136;++d) {
    uint32_t bits;memcpy(&bits,&ymulti[q][h][d],4);
    if(h<3 && q*3+h<8 && d<96) assert(ymulti[q][h][d]==expected[q][h][d]);
    else assert(bits==0xa5a5a5a5u);
  }
  printf("PREFILL_EXECUTE_PASS kv_heads=2 queries=5 gqa=3 tail_rows=7 all_outputs=1 fallback_no_callbacks=1\n");
}
