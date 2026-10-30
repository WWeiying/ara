/* Freeze only selection; runtime, arithmetic and descriptors remain shared. */
#include "selector_baseline_runtime.h"
#include "software/akv/experimental/quantized_kv/selection_strided.h"
#include "selector_baseline.h"
#define akv_quant_select_strided akv_quant_select_strided_baseline
#define akv_quant_strided_workspace_bytes akv_quant_baseline_workspace_bytes
#define akv_quant_strided_execute akv_quant_baseline_execute
#define akv_quant_strided_execute_grouped_pv akv_quant_baseline_execute_grouped_pv
#include "software/akv/experimental/quantized_kv/runtime_strided.c"
#undef akv_quant_select_strided
#undef akv_quant_strided_workspace_bytes
#undef akv_quant_strided_execute
#undef akv_quant_strided_execute_grouped_pv
