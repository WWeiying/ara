#include "native.h"

size_t akv_quant_native_workspace_bytes(void) {
  return sizeof(akv_quant_native_workspace_t);
}

size_t akv_quant_native_workspace_alignment(void) {
  return 64;
}

int akv_quant_native_execute(const akv_quant_selection_input_t *input,
    const akv_quant_native_bindings_t *bindings, void *workspace,
    size_t workspace_bytes, akv_quant_native_report_t *report) {
  if (!report) return AKV_QUANT_NATIVE_FALLBACK;
  if (!workspace || ((uintptr_t)workspace & 63u) ||
      workspace_bytes < sizeof(akv_quant_native_workspace_t)) {
    memset(report, 0, sizeof(*report));
    report->selection_reason = AKV_QUANT_SELECT_LAYOUT;
    return AKV_QUANT_NATIVE_FALLBACK;
  }
  return akv_quant_native_run(input, bindings, workspace, report);
}
