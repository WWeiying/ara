#include "runtime.h"
#include "online.h"

/* Preserve the reviewed selector, descriptor, gather and completion paths.
 * online.h has already included the old schedule, so this remaps only its
 * runtime call site. Public names remain distinct from the production entry. */
#define quant_register_online akv_output_tile_online
#define quant_register_execute quant_output_tile_inner_execute
#define quant_register_workspace_bytes quant_output_tile_workspace_bytes
#define quant_register_unused_grouped_execute quant_output_tile_unused_grouped_execute
#include "software/akv/experimental/quantized_kv/register_pv/runtime.c"
#undef quant_register_unused_grouped_execute
#undef quant_register_workspace_bytes
#undef quant_register_execute
#undef quant_register_online

int quant_output_tile_execute(const akv_quant_selection_input_t *input,
    const akv_quant_native_bindings_t *bindings, void *workspace,
    size_t bytes, akv_quant_strided_report_t *report) {
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
  return quant_output_tile_inner_execute(input,bindings,workspace,bytes,report);
}
