#ifndef QBS_DECODE_SUMS_CANDIDATE_H
#define QBS_DECODE_SUMS_CANDIDATE_H

#include <stddef.h>
#include <stdint.h>
#include <riscv_vector.h>

// Caller supplies complete 16-byte groups, vl <= VLMAX(e8,m2), VLEN >= 128.
static inline void qbs_decode_sums_candidate(vint8m2_t values, size_t vl, int16_t *out) {
    const size_t register_bytes = __riscv_vsetvlmax_e8m1();
    const vint16m1_t zero = __riscv_vmv_v_x_i16m1(0, 1);
    for (size_t offset = 0; offset < vl; offset += 16) {
        const vint8m1_t part = offset < register_bytes
            ? __riscv_vget_v_i8m2_i8m1(values, 0)
            : __riscv_vget_v_i8m2_i8m1(values, 1);
        const size_t local = offset < register_bytes ? offset : offset - register_bytes;
        const vint8m1_t group = __riscv_vslidedown_vx_i8m1(part, local, 16);
        const vint16m1_t sum = __riscv_vwredsum_vs_i8m1_i16m1(group, zero, 16);
        out[offset / 16] = __riscv_vmv_x_s_i16m1_i16(sum);
    }
}

#endif
