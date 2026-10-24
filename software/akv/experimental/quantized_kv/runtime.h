#ifndef AKV_QUANTIZED_KV_RUNTIME_H
#define AKV_QUANTIZED_KV_RUNTIME_H

#include "selection.h"

#ifdef __cplusplus
extern "C" {
#endif

/* C ABI boundary for a C++ GGML adapter. Arithmetic stays in the same C
 * implementation used by native benchmarks, with explicit compiler FP policy. */
typedef struct {
  void (*quantize)(const float *, void *, int64_t);
  void (*decode)(const void *, float *, int64_t);
  void (*scale)(int, float *, float);
  void (*mad)(int, float *, const float *, float);
  qbs_command_executor_t execute;
  void *executor_context;
} akv_quant_native_bindings_t;

enum {
  AKV_QUANT_NATIVE_OK = 0,
  AKV_QUANT_NATIVE_FALLBACK = 1,
  AKV_QUANT_NATIVE_EXECUTION_FAILED = 2,
};

typedef struct {
  unsigned selection_reason, completed_groups, command_attempts, value_decodes;
  qbs_status_t executor_status;
} akv_quant_native_report_t;

size_t akv_quant_native_workspace_bytes(void);
size_t akv_quant_native_workspace_alignment(void);
int akv_quant_native_execute(const akv_quant_selection_input_t *input,
    const akv_quant_native_bindings_t *bindings, void *workspace,
    size_t workspace_bytes, akv_quant_native_report_t *report);

#ifdef __cplusplus
}
#endif
#endif
