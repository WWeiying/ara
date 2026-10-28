#ifndef QUANT_PREFILL_EXECUTE_PLANNED_H
#define QUANT_PREFILL_EXECUTE_PLANNED_H
#include "execute.h"
#include "boundary_cost_bounded.h"

/* Independent experiment; not installed in GGML. Same caller ownership and
 * failure contract as the accepted entry; planning cost must be measured. */
static inline int quant_prefill_execute_planned(const quant_prefill_input_t *request,
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
  unsigned flat_visible[QUANT_PREFILL_MAX_QUERIES*AKV_QUANT_MAX_HEADS];
  unsigned sizes[(QUANT_PREFILL_MAX_QUERIES*AKV_QUANT_MAX_HEADS+7)/8];
  for(unsigned row=0;row<total;++row)flat_visible[row]=admission.visible[row/gqa];
  unsigned groups=prefill_plan_boundaries_bounded(flat_visible,total,sizes);
  for(unsigned kv=0;kv<admission.common.kv_heads;++kv)
    for(unsigned group=0,first=0;group<groups;first+=sizes[group],++group) {
      unsigned rows=sizes[group];
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
