#ifndef QUANT_PREFILL_EXECUTE_H
#define QUANT_PREFILL_EXECUTE_H

#include "admission.h"
#include "prefix_panel.h"

typedef struct __attribute__((aligned(64))) {
  akv_quant_native_workspace_t core;
  quant_prefill_panel_context_t panel;
  float output[AKV_QUANT_MAX_HEADS][AKV_QUANT_MAX_DIM];
} quant_prefill_workspace_t;
typedef struct {
  akv_quant_native_report_t native;
  unsigned queries_quantized, alignment_copies, key_panels;
  size_t key_bytes;
} quant_prefill_report_t;

/* Experimental C entry, not installed in GGML. Caller owns a disjoint report,
 * immutable accessible inputs, and serial synchronous execution. FALLBACK is
 * possible only before callbacks/output writes; execution failure is terminal. */
static inline int quant_prefill_execute(const quant_prefill_input_t *request,
    const akv_quant_native_bindings_t *bindings, void *scratch, size_t bytes,
    quant_prefill_report_t *report) {
  if(!report) return AKV_QUANT_NATIVE_FALLBACK;
  memset(report,0,sizeof(*report));
  if(!bindings || !bindings->quantize || !bindings->decode || !bindings->scale ||
      !bindings->mad || !bindings->execute) {
    report->native.selection_reason=AKV_QUANT_SELECT_FEATURE;
    return AKV_QUANT_NATIVE_FALLBACK;
  }
  if(!scratch || (uintptr_t)scratch%64 || bytes<sizeof(quant_prefill_workspace_t) ||
      sizeof(quant_prefill_workspace_t)>UINTPTR_MAX-(uintptr_t)scratch) {
    report->native.selection_reason=AKV_QUANT_SELECT_LAYOUT;
    return AKV_QUANT_NATIVE_FALLBACK;
  }
  quant_prefill_admission_t admission;
  report->native.selection_reason=quant_prefill_admit(request,&admission);
  if(report->native.selection_reason!=AKV_QUANT_SELECT_OK) return AKV_QUANT_NATIVE_FALLBACK;
  const akv_quant_selection_input_t *input=&request->tensors;
  const akv_quant_tensor_view_t *views[]={&input->query,&input->key,&input->value,&input->output};
  for(unsigned i=0;i<4;++i)
    if(akv_quant_overlap(scratch,sizeof(quant_prefill_workspace_t),views[i]->data,views[i]->bytes)) {
      report->native.selection_reason=AKV_QUANT_SELECT_ALIAS;
      return AKV_QUANT_NATIVE_FALLBACK;
    }
  if(akv_quant_overlap(scratch,sizeof(quant_prefill_workspace_t),input->mask,input->mask_bytes)) {
    report->native.selection_reason=AKV_QUANT_SELECT_ALIAS;
    return AKV_QUANT_NATIVE_FALLBACK;
  }
  quant_prefill_workspace_t *w=scratch;
  const unsigned gqa=admission.common.group_heads;
  const unsigned total=admission.queries*gqa,dim=admission.common.dim;
  for(unsigned kv=0;kv<admission.common.kv_heads;++kv)
    for(unsigned first=0;first<total;first+=AKV_QUANT_MAX_HEADS) {
      unsigned rows=total-first;
      if(rows>AKV_QUANT_MAX_HEADS) rows=AKV_QUANT_MAX_HEADS;
      unsigned visible[AKV_QUANT_MAX_HEADS];
      akv_quant_selection_t selection=admission.common;
      selection.group_heads=rows;selection.visible_tokens=0;
      w->panel.valid=0;w->panel.panels=0;w->panel.copied_bytes=0;
      w->panel.native.alignment_copies=0;
      w->panel.native.core=(akv_quant_native_context_t){input,bindings,&selection,&w->core,&report->native,kv};
      w->panel.native.visible=visible;
      for(unsigned row=0;row<rows;++row) {
        const unsigned q=(first+row)/gqa,h=kv*gqa+(first+row)%gqa;
        visible[row]=admission.visible[q];
        if(visible[row]>selection.visible_tokens) selection.visible_tokens=visible[row];
        const float *source=(const float *)((const unsigned char *)input->query.data+
            q*input->query.token_stride+h*input->query.head_stride);
        bindings->quantize(source,w->core.query+row*selection.query_quant_row_bytes,dim);
        ++report->queries_quantized;
      }
      akv_quant_online_plan_t plan={rows,dim,selection.visible_tokens,input->scale,
        &w->panel,quant_prefill_panel_qk,quant_prefill_panel_value,bindings->scale,bindings->mad};
      int status=quant_prefill_prefix_schedule(&plan,visible,w->output[0],AKV_QUANT_MAX_DIM,&w->core.online);
      w->panel.native.visible=NULL;
      w->panel.native.core.selection=NULL;
      report->alignment_copies+=w->panel.native.alignment_copies;
      report->key_panels+=w->panel.panels;report->key_bytes+=w->panel.copied_bytes;
      if(status!=AKV_QUANT_OK) return AKV_QUANT_NATIVE_EXECUTION_FAILED;
      for(unsigned row=0;row<rows;++row) {
        const unsigned q=(first+row)/gqa,h=kv*gqa+(first+row)%gqa;
        void *destination=(unsigned char *)input->output.data+
          q*input->output.token_stride+h*input->output.head_stride;
        memcpy(destination,w->output[row],dim*sizeof(float));
      }
      ++report->native.completed_groups;
    }
  return AKV_QUANT_NATIVE_OK;
}
#endif
