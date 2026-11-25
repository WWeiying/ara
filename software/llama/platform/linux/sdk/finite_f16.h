#ifndef ARA_RESIDENT_FINITE_F16_H
#define ARA_RESIDENT_FINITE_F16_H

#include <stddef.h>
#include <stdint.h>

#if defined(__riscv_vector)
#include <riscv_vector.h>
#endif

/* Integer tests preserve FFLAGS, including for signaling NaN encodings. */
static inline int ara_resident_finite_f16(const uint16_t *p, size_t count)
{
#if defined(__riscv_vector)
    while (count) {
        size_t vl = __riscv_vsetvl_e16m2(count);
        vuint16m2_t x = __riscv_vle16_v_u16m2(p, vl);
        x = __riscv_vand_vx_u16m2(x, 0x7c00u, vl);
        vbool8_t bad = __riscv_vmseq_vx_u16m2_b8(x, 0x7c00u, vl);
        if (__riscv_vcpop_m_b8(bad, vl)) return 0;
        p += vl;
        count -= vl;
    }
#else
    for (size_t i = 0; i < count; ++i)
        if ((p[i] & 0x7c00u) == 0x7c00u) return 0;
#endif
    return 1;
}

#endif
