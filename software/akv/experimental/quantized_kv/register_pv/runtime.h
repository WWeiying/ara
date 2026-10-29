#ifndef QUANT_REGISTER_PV_RUNTIME_CANDIDATE_H
#define QUANT_REGISTER_PV_RUNTIME_CANDIDATE_H

#include "software/akv/experimental/quantized_kv/runtime_strided.h"

/* Opt-in RVV path: production scale/fused-MAD arithmetic and immutable buffers.
 * Same report and workspace layout as the shared strided runtime. */
size_t quant_register_workspace_bytes(void);
int quant_register_execute(const akv_quant_selection_input_t *input,
    const akv_quant_native_bindings_t *bindings, void *workspace,
    size_t workspace_bytes, akv_quant_strided_report_t *report);

#endif
