/* Successor experiment while the promoted runtime is sealed by model tests. */
#include "software/akv/experimental/quantized_kv/register_pv/runtime.h"
#define quant_register_execute quant_register_inner_execute
#include "software/akv/experimental/quantized_kv/register_pv/runtime.c"
#undef quant_register_execute

int quant_register_execute(const akv_quant_selection_input_t *input,
    const akv_quant_native_bindings_t *bindings, void *workspace,
    size_t bytes, akv_quant_strided_report_t *report) {
  uintptr_t vlenb,frm,vstart;
  __asm__ volatile("csrr %0,vlenb;csrr %1,frm;csrr %2,vstart"
                   :"=r"(vlenb),"=r"(frm),"=r"(vstart)::"memory");
  if(vlenb!=128 || frm || vstart) {
    if(report) {
      /* Do not invoke vectorized libc or permit loop-to-memset conversion. */
      volatile unsigned char *p=(volatile unsigned char *)report;
      for(size_t i=0;i<sizeof(*report);++i) p[i]=0;
      report->native.selection_reason=AKV_QUANT_SELECT_CAPABILITY;
    }
    return AKV_QUANT_NATIVE_FALLBACK;
  }
  return quant_register_inner_execute(input,bindings,workspace,bytes,report);
}
