/* Reuse independent descriptor arithmetic and acceptance checks unchanged.
 * This tests runtime integration, not actual QBS execution or GGML quantization. */
#define quant_register_execute quant_output_tile_execute
#define quant_register_workspace_bytes quant_output_tile_workspace_bytes
#include "verification/akv/quantized_kv/register_pv/test_runtime.c"
