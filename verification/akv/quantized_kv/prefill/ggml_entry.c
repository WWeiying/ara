#include "ggml_entry.h"
#include "ggml_map.h"
#include "execute.h"
#include "software/akv/experimental/quantized_kv/ggml_memory.h"

size_t quant_prefill_ggml_workspace_bytes(void) {
  return sizeof(quant_prefill_workspace_t);
}

size_t quant_prefill_ggml_workspace_alignment(void) { return 64; }

int quant_prefill_ggml_execute(const struct ggml_tensor *dst,
    const akv_quant_ggml_context_t *context,
    const akv_quant_native_bindings_t *bindings, void *workspace, size_t bytes,
    quant_prefill_ggml_report_t *report) {
  if (!report) return AKV_QUANT_NATIVE_FALLBACK;
  memset(report, 0, sizeof(*report));
  quant_prefill_input_t input;
  report->mapping_reason = quant_prefill_ggml_map(dst, context, &input);
  if (report->mapping_reason != AKV_QUANT_GGML_MAP_OK)
    return AKV_QUANT_NATIVE_FALLBACK;
  akv_quant_ggml_context_t checked;
  if (!akv_quant_ggml_memory_context(dst, context, &checked))
    return AKV_QUANT_NATIVE_FALLBACK;
  report->memory_verified = 1;
  input.tensors.query.bytes = checked.query_bytes;
  input.tensors.key.bytes = checked.key_bytes;
  input.tensors.value.bytes = checked.value_bytes;
  input.tensors.mask_bytes = checked.mask_bytes;
  input.tensors.output.bytes = checked.output_bytes;
  quant_prefill_report_t execution;
  report->runtime_called = 1;
  int status = quant_prefill_execute(&input, bindings, workspace, bytes, &execution);
  report->native = execution.native;
  report->queries_quantized = execution.queries_quantized;
  report->alignment_copies = execution.alignment_copies;
  report->key_panels = execution.key_panels;
  report->key_bytes = execution.key_bytes;
  return status;
}
