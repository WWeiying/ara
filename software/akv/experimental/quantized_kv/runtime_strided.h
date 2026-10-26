#ifndef AKV_QUANTIZED_KV_RUNTIME_STRIDED_H
#define AKV_QUANTIZED_KV_RUNTIME_STRIDED_H

#include "runtime.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Successor ABI while the contiguous implementation is sealed by live tests.
 * Gather counters describe copied K bytes, not external-memory transactions. */
typedef struct {
  akv_quant_native_report_t native;
  size_t key_panels, key_bytes;
} akv_quant_strided_report_t;

size_t akv_quant_strided_workspace_bytes(void);
int akv_quant_strided_execute(const akv_quant_selection_input_t *input,
    const akv_quant_native_bindings_t *bindings, void *workspace,
    size_t workspace_bytes, akv_quant_strided_report_t *report);

/* Explicit opt-in for production F32 scale/fused-MAD arithmetic only.
 * Skips intermediate scale/MAD callbacks, retaining final normalization scale.
 * Same workspace/report ABI, admission and post-start failure contract.
 * Fast-math runtime builds reject this opt-in with FALLBACK/FEATURE before
 * quantization, commands or output writes. Post-start errors never fallback.
 * The original entry above keeps its callback schedule and remains default. */
int akv_quant_strided_execute_grouped_pv(const akv_quant_selection_input_t *input,
    const akv_quant_native_bindings_t *bindings, void *workspace,
    size_t workspace_bytes, akv_quant_strided_report_t *report);

#ifdef __cplusplus
}
#endif
#endif
