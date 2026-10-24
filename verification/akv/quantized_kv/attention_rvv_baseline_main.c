/* Both schedules use the same accepted RVV V decoder. The ordinary QK stays
 * production RVV; the shared QK stays QBS. This separates software decoding
 * improvement from QBS plus cross-head scheduling benefit. */
#include "software/akv/experimental/quantized_kv/q8_0_value.h"
#include <stdint.h>

static void fair_value_decode(const void *source, float *output, int64_t elements) {
  akv_quant_q8_0_value(source, output, (size_t)elements);
}

#define dequantize_row_q8_0 fair_value_decode
#include "attention_common_main.c"
#undef dequantize_row_q8_0
