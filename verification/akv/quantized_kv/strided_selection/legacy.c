/* Re-run every sealed strict-selector test against the successor unchanged. */
#include "software/akv/experimental/quantized_kv/selection_strided.h"
#define akv_quant_select akv_quant_select_strided
#include "../test_selection.c"
