#ifndef AKV_QUANTIZED_KV_GROUPED_PV_H
#define AKV_QUANTIZED_KV_GROUPED_PV_H

#include <float.h>
#include <math.h>
#include <stddef.h>
#include <stdint.h>

#if defined(__FAST_MATH__)
#error "grouped PV requires strict floating-point semantics"
#endif
#if FLT_RADIX != 2 || FLT_MANT_DIG != 24 || FLT_MAX_EXP != 128
#error "grouped PV requires IEEE binary32 float"
#endif
#if defined(__riscv_vector)
#include <riscv_vector.h>
#endif

enum { AKV_GROUPED_PV_OK = 0, AKV_GROUPED_PV_BAD_ARGUMENT = 1 };

static inline int akv_grouped_pv_span(const void *p, size_t bytes) {
  return p && (uintptr_t)p % sizeof(float) == 0 &&
         bytes <= UINTPTR_MAX - (uintptr_t)p;
}

static inline int akv_grouped_pv_overlap(const void *a, size_t an,
                                        const void *b, size_t bn) {
  return (uintptr_t)a < (uintptr_t)b + bn &&
         (uintptr_t)b < (uintptr_t)a + an;
}

/* Stride is in floats. Read-only inputs may overlap one another, but not the
 * output span (including padding). Allocation capacities are caller obligations.
 * Coefficients are precomputed; mask records the original rescale branch. */
static inline int akv_grouped_pv_update(unsigned heads, unsigned dim,
    size_t stride, float *output, const float *value, const float *ms,
    const float *vs, unsigned rescale_mask) {
  if (!heads || heads > 8 || dim < 32 || dim > 256 || stride < dim ||
      (rescale_mask >> heads) ||
      (heads > 1 && stride > (SIZE_MAX / sizeof(float) - dim) / (heads - 1)))
    return AKV_GROUPED_PV_BAD_ARGUMENT;
  const size_t yn = ((heads - 1) * stride + dim) * sizeof(float);
  const size_t vn = dim * sizeof(float), cn = heads * sizeof(float);
  if (!akv_grouped_pv_span(output, yn) || !akv_grouped_pv_span(value, vn) ||
      !akv_grouped_pv_span(ms, cn) || !akv_grouped_pv_span(vs, cn) ||
      akv_grouped_pv_overlap(output, yn, value, vn) ||
      akv_grouped_pv_overlap(output, yn, ms, cn) ||
      akv_grouped_pv_overlap(output, yn, vs, cn))
    return AKV_GROUPED_PV_BAD_ARGUMENT;

#if defined(__riscv_vector)
  for (size_t first = 0; first < dim;) {
    const size_t vl = __riscv_vsetvl_e32m4(dim - first);
    const vfloat32m4_t v = __riscv_vle32_v_f32m4(value + first, vl);
    for (unsigned h = 0; h < heads; ++h) {
      float *const dst = output + h * stride + first;
      vfloat32m4_t y = __riscv_vle32_v_f32m4(dst, vl);
      if (rescale_mask & (1u << h))
        y = __riscv_vfmul_vf_f32m4(y, ms[h], vl);
      /* Y is the accumulator; V remains live and unmodified across heads. */
      y = __riscv_vfmacc_vf_f32m4(y, vs[h], v, vl);
      __riscv_vse32_v_f32m4(dst, y, vl);
    }
    first += vl;
  }
#else
  for (unsigned d = 0; d < dim; ++d) {
    const float v = value[d];
    for (unsigned h = 0; h < heads; ++h) {
      float y = output[h * stride + d];
      if (rescale_mask & (1u << h)) {
        volatile float scaled = y * ms[h];
        y = scaled;
      }
      output[h * stride + d] = fmaf(v, vs[h], y);
    }
  }
#endif
  return AKV_GROUPED_PV_OK;
}

#endif
