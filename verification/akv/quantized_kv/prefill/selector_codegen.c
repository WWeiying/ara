#include "selector_aligned.h"
int selector_original_probe(const akv_quant_selection_input_t *p,akv_quant_selection_t *out) {
  return akv_quant_select_strided(p,out);
}
int selector_aligned_probe(const akv_quant_selection_input_t *p,akv_quant_selection_t *out) {
  return akv_quant_select_strided_aligned(p,out);
}
