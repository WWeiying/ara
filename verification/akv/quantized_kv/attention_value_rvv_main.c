/* Keep the ordinary schedule and all checks unchanged. Only the admitted
 * public runtime receives the independently verified finite Q8_0 decoder. */
#include "software/akv/experimental/quantized_kv/runtime.h"
#include "software/akv/experimental/quantized_kv/q8_0_value.h"

static void value_rvv_decode(const void *source, float *output, int64_t elements) {
  akv_quant_q8_0_value(source, output, (size_t)elements);
}

static int value_rvv_execute(const akv_quant_selection_input_t *input,
    const akv_quant_native_bindings_t *bindings, void *workspace,
    size_t workspace_bytes, akv_quant_native_report_t *report) {
  akv_quant_native_bindings_t selected = *bindings;
  selected.decode = value_rvv_decode;
  return akv_quant_native_execute(input, &selected, workspace, workspace_bytes, report);
}

#define akv_quant_native_execute value_rvv_execute
#include "attention_common_main.c"
#undef akv_quant_native_execute
