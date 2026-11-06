#ifndef AKV_OUTPUT_TILE_RUNTIME_H
#define AKV_OUTPUT_TILE_RUNTIME_H
#include "software/akv/experimental/quantized_kv/runtime_strided.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Experimental explicit entry. value_decodes retains the parent report's
 * logical row count, not the number of physical pairwise V re-decodes. */
size_t quant_output_tile_workspace_bytes(void);
int quant_output_tile_execute(const akv_quant_selection_input_t *input,
    const akv_quant_native_bindings_t *bindings, void *workspace,
    size_t bytes, akv_quant_strided_report_t *report);
#ifdef __cplusplus
}
#endif
#endif
