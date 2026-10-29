#ifndef AKV_REGISTER_PV_GGML_ENTRY_H
#define AKV_REGISTER_PV_GGML_ENTRY_H

#include "../ggml_entry_strided.h"
#include "runtime.h"

static inline int quant_register_ggml_execute(const struct ggml_tensor *dst,
    const akv_quant_ggml_context_t *context, const akv_quant_native_bindings_t *bindings,
    void *workspace, size_t workspace_bytes, akv_quant_ggml_strided_report_t *report) {
  if (!report) return AKV_QUANT_NATIVE_FALLBACK;
  memset(report, 0, sizeof(*report));
  akv_quant_selection_input_t input;
  report->mapping_reason = akv_quant_ggml_map(dst, context, &input);
  if (report->mapping_reason != AKV_QUANT_GGML_MAP_OK)
    return AKV_QUANT_NATIVE_FALLBACK;
  if (!akv_quant_ggml_host_extent(dst->src[0], &input.query.bytes) ||
      !akv_quant_ggml_host_extent(dst->src[1], &input.key.bytes) ||
      !akv_quant_ggml_host_extent(dst->src[2], &input.value.bytes) ||
      !akv_quant_ggml_host_extent(dst->src[3], &input.mask_bytes) ||
      !akv_quant_ggml_host_extent(dst, &input.output.bytes))
    return AKV_QUANT_NATIVE_FALLBACK;
  report->memory_verified = 1;
  report->runtime_called = 1;
  return quant_register_execute(&input, bindings, workspace, workspace_bytes,
                                &report->execution);
}

#endif
