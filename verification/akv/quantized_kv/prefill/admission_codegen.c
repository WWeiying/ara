#include "admission_aligned.h"
int admission_original_probe(const quant_prefill_input_t *p,quant_prefill_admission_t *out) {
  return quant_prefill_admit(p,out);
}
int admission_aligned_probe(const quant_prefill_input_t *p,quant_prefill_admission_t *out) {
  return quant_prefill_admit_aligned(p,out);
}
