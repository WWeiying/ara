#define main decode_fixture_main
#include "verification/akv/quantized_kv/test_native.c"
#undef main
#include "prefix_panel.h"

static quant_prefill_panel_context_t panel;
static unsigned char padded_keys[65*144] __attribute__((aligned(64)));
typedef struct {
  const akv_quant_selection_input_t *input;
  unsigned row_bytes, calls, fail;
} panel_executor_t;

static qbs_status_t panel_execute(void *opaque,const qbs_descriptor_t *descriptor,
    unsigned m,const void *activation,float *out,size_t stride,unsigned n,int segmented) {
  panel_executor_t *e=opaque;
  ++e->calls;
  if(e->fail) return QBS_STATUS_EXECUTION;
  qbs_descriptor_fields_t fields=qbs_unpack_descriptor_header(descriptor->header);
  assert(!segmented && fields.n==n && fields.k_blocks==e->input->query.dim/32 &&
         m<=4 && n<=32 && !((uintptr_t)activation&3u));
  const unsigned char *key=(const void *)(uintptr_t)descriptor->weight_base;
  assert(key==panel.key && panel.valid && n<=panel.count && panel.first+n<=65);
  for(unsigned i=0;i<n;++i)
    assert(!memcmp(key+i*e->row_bytes,
                   padded_keys+(panel.first+i)*e->input->key.token_stride,e->row_bytes));
  float packed[128]; qbs_ref_result_t report;
  assert(qbs_ref_execute(descriptor,m,8,1024,(uintptr_t)activation,key,n*e->row_bytes,
      activation,m*(e->input->query.dim/32)*34,packed,128,NULL,NULL,&report)==QBS_REF_OK);
  for(unsigned row=0;row<m;++row) memcpy(out+row*stride,packed+row*32,n*sizeof(float));
  return QBS_STATUS_OK;
}

int main(void) {
  assert(qbs_device_init_reference(1024,&device)==QBS_STATUS_OK);
  const unsigned dims[]={32,96,128};
  const unsigned prefixes[][8]={{1,2,3,4,5,6,7,8},{31,31,32,32,33,33,65,65},
                                {65,33,32,31,3,2,1,65},{65,65,65,65,65,65,65,65}};
  unsigned cases=0;
  for(unsigned d=0;d<3;++d) for(unsigned format=0;format<2;++format)
    for(unsigned pattern=0;pattern<4;++pattern) {
      akv_quant_selection_input_t input=prepare(dims[d],8,1,65,format);
      akv_quant_selection_t selection;
      assert(akv_quant_select(&input,&selection)==AKV_QUANT_SELECT_OK);
      executor_t old_executor={.input=&input};
      akv_quant_native_bindings_t bindings={quantize,decode,scale,mad,execute,&old_executor};
      akv_quant_native_report_t report={0};
      memset(&panel,0,sizeof(panel));
      panel.native.core=(akv_quant_native_context_t){&input,&bindings,&selection,&workspace,&report,0};
      panel.native.visible=prefixes[pattern];
      for(unsigned row=0;row<8;++row)
        quantize(query[row],workspace.query+row*selection.query_quant_row_bytes,dims[d]);
      akv_quant_online_plan_t plan={8,dims[d],65,input.scale,&panel,
        quant_prefill_panel_qk,quant_prefill_panel_value,scale,mad};
      assert(quant_prefill_prefix_schedule(&plan,panel.native.visible,reference[0],136,
          &workspace.online)==AKV_QUANT_OK);
      assert(panel.panels==0 && panel.copied_bytes==0);
      const size_t row_bytes=selection.key_row_bytes, pitch=row_bytes+8;
      memset(padded_keys,0xa5,sizeof(padded_keys));
      for(unsigned token=0;token<65;++token)
        memcpy(padded_keys+token*pitch,keys+token*row_bytes,row_bytes);
      akv_quant_selection_input_t strided=input;
      strided.key.data=padded_keys;strided.key.bytes=sizeof(padded_keys);
      strided.key.token_stride=pitch;strided.key.head_stride=65*pitch;
      panel_executor_t execution={&strided,row_bytes,0,0};
      bindings.execute=panel_execute;bindings.executor_context=&execution;
      panel.native.core.input=&strided;
      memset(&report,0,sizeof(report));
      assert(quant_prefill_prefix_schedule(&plan,panel.native.visible,output[0],136,
          &workspace.online)==AKV_QUANT_OK);
      assert(!memcmp(output,reference,sizeof(output)));
      unsigned maximum=0;
      for(unsigned row=0;row<8;++row) if(prefixes[pattern][row]>maximum) maximum=prefixes[pattern][row];
      assert(panel.panels==(maximum+31)/32 && panel.copied_bytes==maximum*row_bytes &&
             report.command_attempts==execution.calls && report.value_decodes==maximum);
      // Reject masked/out-of-tile requests before gathering or execution.
      unsigned calls=execution.calls,panels=panel.panels;
      assert(quant_prefill_panel_qk(&panel,0,1,prefixes[pattern][0],1,output[0],136));
      assert(execution.calls==calls && panel.panels==panels);
      execution.fail=1;panel.valid=0;
      assert(quant_prefill_panel_qk(&panel,0,1,0,1,output[0],136));
      assert(panel.native.core.input==&strided && panel.native.core.selection==&selection &&
             panel.native.visible==prefixes[pattern] && report.executor_status==QBS_STATUS_EXECUTION);
      ++cases;
    }
  printf("PREFIX_PANEL_PASS cases=%u contiguous_no_copy=1 visible_union_once=1 failure_restores_context=1\n",cases);
}
