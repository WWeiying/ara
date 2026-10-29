#include "prefill_prefix_candidate.h"
#include "software/akv/experimental/quantized_kv/prefill/prefix_panel.h"

static int register_prefix_binding(const akv_quant_online_plan_t *p,
    const unsigned *visible,float *output,size_t stride,akv_quant_online_workspace_t *w) {
  quant_prefill_panel_context_t *c=p->context;
  const akv_quant_tensor_view_t *v=&c->native.core.input->value;
  const size_t offset=c->native.core.kv_head*v->head_stride;
  const quant_register_pv_view_t view={
    (const unsigned char *)v->data+offset,v->token_stride,v->bytes-offset};
  const int status=quant_register_prefill_prefix(p,visible,output,stride,w,&view);
  if(status==AKV_QUANT_OK) {
    unsigned maximum=0;
    for(unsigned row=0;row<p->heads;++row) if(visible[row]>maximum) maximum=visible[row];
    c->native.core.report->value_decodes+=maximum;
  }
  return status;
}

/* Keep admission, quantization, panel gathering, QBS and scatter canonical. */
#define quant_prefill_prefix_schedule register_prefix_binding
#define quant_prefill_execute register_prefill_internal_execute
#include "software/akv/experimental/quantized_kv/prefill/execute.h"
#undef quant_prefill_execute
#undef quant_prefill_prefix_schedule

int quant_prefill_register_execute(const quant_prefill_input_t *request,
    const akv_quant_native_bindings_t *bindings,void *scratch,size_t bytes,
    quant_prefill_report_t *report) {
  uintptr_t vlenb,frm,vstart;
  __asm__ volatile("csrr %0,vlenb;csrr %1,frm;csrr %2,vstart"
                   :"=r"(vlenb),"=r"(frm),"=r"(vstart)::"memory");
  if(vlenb!=128 || frm || vstart) {
    if(report) {
      volatile unsigned char *p=(volatile unsigned char *)report;
      for(size_t i=0;i<sizeof(*report);++i) p[i]=0;
      report->native.selection_reason=AKV_QUANT_SELECT_CAPABILITY;
    }
    return AKV_QUANT_NATIVE_FALLBACK;
  }
  return register_prefill_internal_execute(request,bindings,scratch,bytes,report);
}
