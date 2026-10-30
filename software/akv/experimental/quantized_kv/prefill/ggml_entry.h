#ifndef QUANT_PREFILL_GGML_ENTRY_H
#define QUANT_PREFILL_GGML_ENTRY_H

#include "software/akv/experimental/quantized_kv/ggml_decode.h"
#include "software/akv/experimental/quantized_kv/runtime.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
  unsigned mapping_reason, memory_verified, runtime_called;
  akv_quant_native_report_t native;
  unsigned queries_quantized, alignment_copies, key_panels;
  size_t key_bytes;
} quant_prefill_ggml_report_t;

size_t quant_prefill_ggml_workspace_bytes(void);
size_t quant_prefill_ggml_workspace_alignment(void);

/* Opt-in entry used by the GGML quantized-Prefill backend. Caller owns a
 * disjoint report/workspace and immutable tensor objects. Backend host extent
 * checks do not replace the caller's normal-memory/coherency assertion.
 * FALLBACK is pre-execution only; EXECUTION_FAILED must never be retried. */
int quant_prefill_ggml_execute(const struct ggml_tensor *dst,
    const akv_quant_ggml_context_t *context,
    const akv_quant_native_bindings_t *bindings, void *workspace, size_t bytes,
    quant_prefill_ggml_report_t *report);

#ifdef __cplusplus
}
#endif
#endif
