#ifndef QUANT_SELECTOR_BASELINE_RUNTIME_H
#define QUANT_SELECTOR_BASELINE_RUNTIME_H
#include "software/akv/experimental/quantized_kv/runtime_strided.h"
size_t akv_quant_baseline_workspace_bytes(void);
int akv_quant_baseline_execute(const akv_quant_selection_input_t *,
    const akv_quant_native_bindings_t *,void *,size_t,akv_quant_strided_report_t *);
#endif
