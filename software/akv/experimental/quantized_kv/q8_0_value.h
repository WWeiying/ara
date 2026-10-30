#ifndef AKV_QUANTIZED_KV_Q8_0_VALUE_H
#define AKV_QUANTIZED_KV_Q8_0_VALUE_H

#include <riscv_vector.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "field_copy.h"

/* Exact Q8_0 encoding only: F16 scale then 32 signed bytes. The caller must
 * provide disjoint valid buffers, elements divisible by 32, and finite scales.
 * This changes only V decoding, not Query quantization or PV accumulation.
 * Integer conversion and scale multiplication are exact in F32 for this
 * finite-F16/signed-eight-bit domain; no reduction or FMA is introduced. */
static inline void akv_quant_q8_0_value(const void *source, float *output, size_t elements) {
  const unsigned char *block = (const unsigned char *)source;
  for (size_t first = 0; first < elements; first += 32, block += 34) {
    _Float16 half_scale;
    AKV_QUANT_FIELD_COPY(&half_scale, block, sizeof(half_scale));
    const float scale = (float)half_scale;
    for (size_t offset = 0; offset < 32;) {
      const size_t vl = __riscv_vsetvl_e8mf2(32 - offset);
      const vint8mf2_t bytes = __riscv_vle8_v_i8mf2((const int8_t *)block + 2 + offset, vl);
      const vint32m2_t integers = __riscv_vsext_vf4_i32m2(bytes, vl);
      const vfloat32m2_t values = __riscv_vfcvt_f_x_v_f32m2(integers, vl);
      __riscv_vse32_v_f32m2(output + first + offset,
                          __riscv_vfmul_vf_f32m2(values, scale, vl), vl);
      offset += vl;
    }
  }
}

#endif
