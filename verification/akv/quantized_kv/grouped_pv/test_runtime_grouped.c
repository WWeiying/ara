/* Reuse the independently checked panel/lifetime fixture without changing its
 * contiguous reference arm or the production implementation. */
#define akv_quant_strided_execute akv_quant_strided_execute_grouped_pv
#include "verification/akv/quantized_kv/test_native_strided.c"
#undef akv_quant_strided_execute
