#include "selector_runtime.h"
#include "selector_block_max.h"

/* Identical runtime/descriptor/arithmetic source, independent selector only. */
#define akv_quant_select_strided akv_quant_select_strided_block_max
#define akv_quant_strided_workspace_bytes akv_quant_selector_workspace_bytes
#define akv_quant_strided_execute akv_quant_selector_execute
#define akv_quant_strided_execute_grouped_pv akv_quant_selector_execute_grouped_pv
#include "software/akv/experimental/quantized_kv/runtime_strided.c"
#undef akv_quant_select_strided
#undef akv_quant_strided_workspace_bytes
#undef akv_quant_strided_execute
#undef akv_quant_strided_execute_grouped_pv
