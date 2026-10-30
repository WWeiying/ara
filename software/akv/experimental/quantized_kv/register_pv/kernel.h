#ifndef QUANT_REGISTER_PV_CANDIDATE_H
#define QUANT_REGISTER_PV_CANDIDATE_H

#include "software/akv/experimental/quantized_kv/grouped_pv.h"
#include "software/akv/experimental/quantized_kv/field_copy.h"

/* Experimental internal leaf, not installed in the runtime. RNE, finite Q8_0
 * scales, masked FP traps and no intermediate FFLAGS observation are required.
 * Buffer capacities/immutability are caller obligations, as for grouped PV.
 * Register fragments below are 32 floats only when vlenb==128. Other machines
 * reject before a vector instruction/output write; callers retain fallback. */
/* A non-inlined vector-return helper would impose ABI saves at every block. */
static inline __attribute__((always_inline)) vfloat32m1_t
quant_register_pv_decode(const unsigned char *block) {
  _Float16 half;
  AKV_QUANT_FIELD_COPY(&half, block, sizeof(half));
  const float scale = (float)half;
  const size_t vl = __riscv_vsetvl_e8mf4(32);
  const vint8mf4_t bytes = __riscv_vle8_v_i8mf4((const int8_t *)block+2, vl);
  const vint32m1_t integers = __riscv_vsext_vf4_i32m1(bytes, vl);
  return __riscv_vfmul_vf_f32m1(__riscv_vfcvt_f_x_v_f32m1(integers, vl), scale, vl);
}

static inline int quant_register_pv_update(unsigned heads, unsigned dim,
    size_t stride, float *output, const void *source, const float *ms,
    const float *vs, unsigned rescale_mask) {
  if (!heads || heads>8 || dim<32 || dim>256 || dim%32 || stride<dim ||
      (rescale_mask>>heads) || akv_grouped_pv_stride_exceeds(stride, heads-1,
          SIZE_MAX/sizeof(float)-dim)) return AKV_GROUPED_PV_BAD_ARGUMENT;
  const size_t yn=((heads-1)*stride+dim)*sizeof(float);
  const size_t sn=dim/32*34, cn=heads*sizeof(float);
  if (!akv_grouped_pv_span(output,yn) || !source ||
      sn>UINTPTR_MAX-(uintptr_t)source ||
      !akv_grouped_pv_span(ms,cn) || !akv_grouped_pv_span(vs,cn) ||
      akv_grouped_pv_overlap(output,yn,source,sn) ||
      akv_grouped_pv_overlap(output,yn,ms,cn) ||
      akv_grouped_pv_overlap(output,yn,vs,cn)) return AKV_GROUPED_PV_BAD_ARGUMENT;
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
  if (vlenb!=128) return AKV_GROUPED_PV_BAD_ARGUMENT;
  for (unsigned first=0;first<dim;first+=128) {
    const unsigned left=dim-first;
    const unsigned char *block=(const unsigned char *)source+first/32*34;
    vfloat32m4_t value=__riscv_vundefined_f32m4();
    value=__riscv_vset_v_f32m1_f32m4(value,0,quant_register_pv_decode(block));
    if (left>32)
      value=__riscv_vset_v_f32m1_f32m4(value,1,quant_register_pv_decode(block+34));
    if (left>64)
      value=__riscv_vset_v_f32m1_f32m4(value,2,quant_register_pv_decode(block+68));
    if (left>96)
      value=__riscv_vset_v_f32m1_f32m4(value,3,quant_register_pv_decode(block+102));
    const size_t vl=__riscv_vsetvl_e32m4(left<128?left:128);
    for (unsigned head=0;head<heads;++head) {
      float *dst=output+head*stride+first;
      vfloat32m4_t y=__riscv_vle32_v_f32m4(dst,vl);
      if (rescale_mask & (1u<<head)) y=__riscv_vfmul_vf_f32m4(y,ms[head],vl);
      y=__riscv_vfmacc_vf_f32m4(y,vs[head],value,vl);
      __riscv_vse32_v_f32m4(dst,y,vl);
    }
  }
  return AKV_GROUPED_PV_OK;
}

#endif
