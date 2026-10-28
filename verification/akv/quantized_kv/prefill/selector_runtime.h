#ifndef QUANT_SELECTOR_RUNTIME_EXPERIMENT_H
#define QUANT_SELECTOR_RUNTIME_EXPERIMENT_H
#include "software/akv/experimental/quantized_kv/runtime_strided.h"
#ifdef __cplusplus
extern "C" {
#endif
size_t akv_quant_selector_workspace_bytes(void);
int akv_quant_selector_execute(const akv_quant_selection_input_t *,
    const akv_quant_native_bindings_t *,void *,size_t,akv_quant_strided_report_t *);
int akv_quant_selector_execute_grouped_pv(const akv_quant_selection_input_t *,
    const akv_quant_native_bindings_t *,void *,size_t,akv_quant_strided_report_t *);
#ifdef __cplusplus
}
#endif
#endif
