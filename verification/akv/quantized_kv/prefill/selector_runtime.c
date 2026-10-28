#include "selector_runtime.h"
#include "selector_aligned.h"

/* Independent translation unit: same canonical execution source, only selector
 * and exported symbol names differ. Never override production library objects. */
#define akv_quant_select_strided akv_quant_select_strided_aligned
#define akv_quant_strided_workspace_bytes akv_quant_selector_workspace_bytes
#define akv_quant_strided_execute akv_quant_selector_execute
#define akv_quant_strided_execute_grouped_pv akv_quant_selector_execute_grouped_pv
#include "software/akv/experimental/quantized_kv/runtime_strided.c"
#undef akv_quant_select_strided
#undef akv_quant_strided_workspace_bytes
#undef akv_quant_strided_execute
#undef akv_quant_strided_execute_grouped_pv
