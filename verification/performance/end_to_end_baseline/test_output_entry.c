/* The same public-entry CSR rejection contract applies to the new schedule. */
#define quant_register_execute quant_output_tile_execute
#define quant_register_workspace_bytes quant_output_tile_workspace_bytes
#include "verification/akv/quantized_kv/register_pv/test_entry_guards.c"
