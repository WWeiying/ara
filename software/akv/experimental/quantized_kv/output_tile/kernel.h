#ifndef AKV_QUANT_OUTPUT_TILE_KERNEL_H
#define AKV_QUANT_OUTPUT_TILE_KERNEL_H

#include "software/akv/experimental/quantized_kv/register_pv/kernel.h"
#include "software/akv/experimental/quantized_kv/online.h"

typedef struct {
  float ms[AKV_QUANT_MAX_HEADS][AKV_QUANT_TILE];
  float vs[AKV_QUANT_MAX_HEADS][AKV_QUANT_TILE];
  unsigned rescale[AKV_QUANT_TILE];
} akv_output_tile_coefficients_t;

/* Experimental leaf only. The enclosing schedule must establish immutable,
 * accessible inputs, finite Q8_0 scales, masked FP traps, and no intermediate
 * fflags observation. Token order and conditional rescaling are unchanged.
 * Pairing bounds live output registers; additional pairs decode V again. */
static __attribute__((noinline)) int akv_output_tile_update(
    unsigned heads, unsigned dim, size_t stride, float *output,
    const void *source, size_t token_stride, size_t source_bytes,
    unsigned tokens, const akv_output_tile_coefficients_t *coeff) {
#if defined(__FAST_MATH__)
  (void)heads; (void)dim; (void)stride; (void)output; (void)source;
  (void)token_stride; (void)source_bytes; (void)tokens; (void)coeff;
  return AKV_GROUPED_PV_BAD_ARGUMENT;
#else
  uintptr_t vlenb, frm, vstart;
  __asm__ volatile("csrr %0,vlenb; csrr %1,frm; csrr %2,vstart"
                   : "=r"(vlenb), "=r"(frm), "=r"(vstart) :: "memory");
  if (vlenb != 128 || frm != 0 || vstart != 0 || !heads || heads > 8 ||
      dim < 32 || dim > 256 || dim % 32 || stride < dim ||
      !tokens || tokens > AKV_QUANT_TILE ||
      akv_grouped_pv_stride_exceeds(stride, heads-1, SIZE_MAX/sizeof(float)-dim))
    return AKV_GROUPED_PV_BAD_ARGUMENT;
  const size_t row = dim/32*34;
  const size_t output_bytes = ((heads-1)*stride+dim)*sizeof(float);
  if (token_stride < row || source_bytes < row ||
      akv_grouped_pv_stride_exceeds(token_stride, tokens-1, source_bytes-row) ||
      !source || source_bytes > UINTPTR_MAX-(uintptr_t)source ||
      !akv_grouped_pv_span(output, output_bytes) ||
      !akv_grouped_pv_span(coeff, sizeof(*coeff)) ||
      (uintptr_t)coeff % __alignof__(*coeff) ||
      (uintptr_t)output % __alignof__(float) ||
      akv_grouped_pv_overlap(output, output_bytes, source, source_bytes) ||
      akv_grouped_pv_overlap(output, output_bytes, coeff, sizeof(*coeff)))
    return AKV_GROUPED_PV_BAD_ARGUMENT;
  for (unsigned t=0; t<tokens; ++t)
    if (coeff->rescale[t] >> heads) return AKV_GROUPED_PV_BAD_ARGUMENT;

  for (unsigned head=0; head<heads; head+=2) {
    const int paired = head+1 < heads;
    for (unsigned first=0; first<dim; first+=128) {
      const unsigned left = dim-first < 128 ? dim-first : 128;
      const size_t vl = __riscv_vsetvl_e32m4(left);
      float *dst0 = output + head*stride + first;
      float *dst1 = paired ? dst0+stride : dst0;
      vfloat32m4_t y0 = __riscv_vle32_v_f32m4(dst0, vl);
      vfloat32m4_t y1 = __riscv_vundefined_f32m4();
      if (paired) y1 = __riscv_vle32_v_f32m4(dst1, vl);
      for (unsigned t=0; t<tokens; ++t) {
        const unsigned char *block = (const unsigned char *)source + t*token_stride + first/32*34;
        vfloat32m4_t value = __riscv_vundefined_f32m4();
        value = __riscv_vset_v_f32m1_f32m4(value, 0, quant_register_pv_decode(block));
        if (left > 32)
          value = __riscv_vset_v_f32m1_f32m4(value, 1, quant_register_pv_decode(block+34));
        if (left > 64)
          value = __riscv_vset_v_f32m1_f32m4(value, 2, quant_register_pv_decode(block+68));
        if (left > 96)
          value = __riscv_vset_v_f32m1_f32m4(value, 3, quant_register_pv_decode(block+102));
        if (coeff->rescale[t] & (1u << head))
          y0 = __riscv_vfmul_vf_f32m4(y0, coeff->ms[head][t], vl);
        y0 = __riscv_vfmacc_vf_f32m4(y0, coeff->vs[head][t], value, vl);
        if (paired) {
          if (coeff->rescale[t] & (1u << (head+1)))
            y1 = __riscv_vfmul_vf_f32m4(y1, coeff->ms[head+1][t], vl);
          y1 = __riscv_vfmacc_vf_f32m4(y1, coeff->vs[head+1][t], value, vl);
        }
      }
      __riscv_vse32_v_f32m4(dst0, y0, vl);
      if (paired) __riscv_vse32_v_f32m4(dst1, y1, vl);
    }
  }
  return AKV_GROUPED_PV_OK;
#endif
}

#endif
