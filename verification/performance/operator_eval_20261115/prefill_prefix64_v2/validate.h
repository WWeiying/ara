#ifndef PREFILL_COMPACT_VALIDATE_H
#define PREFILL_COMPACT_VALIDATE_H
#include <math.h>
#include <stdint.h>
#include <string.h>

typedef struct { unsigned checked, nonfinite, tolerance_errors; } compact_check_t;

#ifdef __riscv_vector
#include <riscv_vector.h>
__attribute__((noinline, noclone)) compact_check_t compact_validate_all(
    const float *actual, const float *gold, unsigned count) {
  compact_check_t report = {0};
  for (unsigned first = 0; first < count;) {
    const size_t vl = __riscv_vsetvl_e32m4(count-first);
    const vfloat32m4_t y = __riscv_vle32_v_f32m4(actual+first, vl);
    const vfloat32m4_t g = __riscv_vle32_v_f32m4(gold+first, vl);
    const vuint32m4_t y_exp = __riscv_vand_vx_u32m4(__riscv_vreinterpret_v_f32m4_u32m4(y), 0x7f800000u, vl);
    const vuint32m4_t g_exp = __riscv_vand_vx_u32m4(__riscv_vreinterpret_v_f32m4_u32m4(g), 0x7f800000u, vl);
    const vbool8_t nonfinite = __riscv_vmor_mm_b8(
        __riscv_vmseq_vx_u32m4_b8(y_exp,0x7f800000u,vl),
        __riscv_vmseq_vx_u32m4_b8(g_exp,0x7f800000u,vl),vl);
    const vfloat32m4_t difference = __riscv_vfabs_v_f32m4(__riscv_vfsub_vv_f32m4(y,g,vl),vl);
    const vfloat32m4_t tolerance = __riscv_vfadd_vf_f32m4(
        __riscv_vfmul_vf_f32m4(__riscv_vfabs_v_f32m4(g,vl),.002f,vl),.004f,vl);
    report.nonfinite += __riscv_vcpop_m_b8(nonfinite,vl);
    report.tolerance_errors += __riscv_vcpop_m_b8(__riscv_vmfgt_vv_f32m4_b8(difference,tolerance,vl),vl);
    report.checked += vl;
    first += vl;
  }
  return report;
}
#else
static compact_check_t compact_validate_all(const float *actual, const float *gold, unsigned count) {
  compact_check_t report = {0};
  for (unsigned i = 0; i < count; ++i) {
    report.nonfinite += !isfinite(actual[i]) || !isfinite(gold[i]);
    report.tolerance_errors += fabsf(actual[i]-gold[i]) > .004f+.002f*fabsf(gold[i]);
    ++report.checked;
  }
  return report;
}
#endif
#endif
