#ifndef QUANTKV_COMPACT_COMPARE_H
#define QUANTKV_COMPACT_COMPARE_H
#include <stddef.h>
#include <stdint.h>
typedef struct { size_t checked; long first_fail; unsigned state_errors; } quantkv_bytes_t;

#ifdef __riscv_vector
#include <riscv_vector.h>
__attribute__((noinline,noclone)) quantkv_bytes_t quantkv_compare_bytes(
    const unsigned char *actual,const unsigned char *expected,size_t bytes) {
  quantkv_bytes_t result={0,-1,0};
  uintptr_t fc,vc,vs,after_fc,after_vc,after_vs;
  __asm__ volatile("frcsr %0\ncsrr %1,vcsr\ncsrr %2,vstart":"=r"(fc),"=r"(vc),"=r"(vs)::"memory");
  /* A nonzero VSTART must not be silently cleared by a vector instruction. */
  if (vs) { result.state_errors=1; return result; }
  while (result.checked<bytes) {
    const size_t vl=__riscv_vsetvl_e8m8(bytes-result.checked);
    const vuint8m8_t a=__riscv_vle8_v_u8m8(actual+result.checked,vl);
    const vuint8m8_t e=__riscv_vle8_v_u8m8(expected+result.checked,vl);
    const vbool1_t equal=__riscv_vmseq_vv_u8m8_b1(a,e,vl);
    const long bad=__riscv_vfirst_m_b1(__riscv_vmnot_m_b1(equal,vl),vl);
    if (bad>=0 && result.first_fail<0) result.first_fail=(long)result.checked+bad;
    result.checked+=vl;
  }
  __asm__ volatile("frcsr %0\ncsrr %1,vcsr\ncsrr %2,vstart":"=r"(after_fc),"=r"(after_vc),"=r"(after_vs)::"memory");
  result.state_errors=fc!=after_fc || vc!=after_vc || vs!=after_vs;
  return result;
}
#else
static quantkv_bytes_t quantkv_compare_bytes(const unsigned char *actual,
    const unsigned char *expected,size_t bytes) {
  quantkv_bytes_t result={0,-1,0};
  /* Small host strips exercise tail and first-failure accounting, without RVV. */
  while (result.checked<bytes) {
    size_t vl=bytes-result.checked; if (vl>13) vl=13;
    for (size_t i=0;i<vl;++i)
      if (actual[result.checked+i]!=expected[result.checked+i] && result.first_fail<0)
        result.first_fail=(long)(result.checked+i);
    result.checked+=vl;
  }
  return result;
}
#endif
#endif
