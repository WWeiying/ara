#include "runtime.h"
#include "online.h"
#include "software/akv/experimental/quantized_kv/selection_strided.h"

/* Include the reviewed implementation, not a fork of its admission, gather,
 * descriptor or completion logic. Header guards keep the original online
 * helper definitions untouched; only the call site below is redirected. */
static int register_runtime_online(const akv_quant_online_plan_t *,float *,
    size_t,akv_quant_online_workspace_t *);

static int register_runtime_select(const akv_quant_selection_input_t *input,
    akv_quant_selection_t *selection) {
  /* Check the actual machine before quantization/commands/output writes,
   * not just the capability fields supplied by the caller. */
  uintptr_t vlenb,frm,vstart;
  __asm__ volatile("csrr %0,vlenb;csrr %1,frm;csrr %2,vstart"
                   :"=r"(vlenb),"=r"(frm),"=r"(vstart));
  if(vlenb!=128 || frm || vstart) return AKV_QUANT_SELECT_CAPABILITY;
  return akv_quant_select_strided(input,selection);
}

#define akv_quant_strided_workspace_bytes quant_register_workspace_bytes
#define akv_quant_strided_execute quant_register_execute
#define akv_quant_strided_execute_grouped_pv quant_register_unused_grouped_execute
#define akv_quant_select_strided register_runtime_select
#define akv_quant_online_shared register_runtime_online
#include "software/akv/experimental/quantized_kv/runtime_strided.c"
#undef akv_quant_online_shared
#undef akv_quant_select_strided
#undef akv_quant_strided_execute_grouped_pv
#undef akv_quant_strided_execute
#undef akv_quant_strided_workspace_bytes

static int register_runtime_online(const akv_quant_online_plan_t *plan,
    float *output,size_t stride,akv_quant_online_workspace_t *workspace) {
  akv_quant_strided_context_t *context=plan->context;
  const akv_quant_tensor_view_t *v=&context->core.input->value;
  /* The unchanged selector proved head offset, extent and finite Q8_0 scales.
   * Never reinterpret total tensor bytes as bytes remaining after head offset. */
  const size_t offset=context->core.kv_head*v->head_stride;
  const quant_register_pv_view_t view={
    (const unsigned char *)v->data+offset,v->token_stride,v->bytes-offset};
  const int status=quant_register_online(plan,output,stride,workspace,&view);
  if(status==AKV_QUANT_OK)
    context->core.report->value_decodes+=plan->tokens;
  /* value_decodes counts processed Q8 rows, not legacy decoder callbacks.
   * On failure the report is incomplete and must not become performance data. */
  return status;
}
