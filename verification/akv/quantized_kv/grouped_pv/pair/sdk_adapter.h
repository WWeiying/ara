#ifndef QUANT_GROUPED_PAIR_SDK_ADAPTER_H
#define QUANT_GROUPED_PAIR_SDK_ADAPTER_H

#include "software/akv/experimental/quantized_kv/runtime_strided.h"

/* API 0 retains the original callbacks; API 1 is the explicit SDK opt-in.
 * No callback instrumentation, inferred update counts or fallback retry. */
static inline int pair_sdk_execute(unsigned enabled,
    const akv_quant_selection_input_t *input,
    const akv_quant_native_bindings_t *bindings, void *workspace, size_t bytes,
    akv_quant_strided_report_t *report) {
  return enabled ? akv_quant_strided_execute_grouped_pv(input, bindings, workspace, bytes, report)
                 : akv_quant_strided_execute(input, bindings, workspace, bytes, report);
}

#endif
