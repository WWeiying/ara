#ifndef QBS_DECODE_SUMS_SPLIT_CANDIDATE_H
#define QBS_DECODE_SUMS_SPLIT_CANDIDATE_H
#include <stddef.h>
#include <stdint.h>
#include <riscv_vector.h>

// Split loops keep a vector-valued select out of the reduction recurrence.
// Caller supplies complete 16-byte groups, vl <= VLMAX(e8,m2), VLEN >= 128.
static inline void qbs_decode_sums_split_candidate(vint8m2_t values, size_t vl, int16_t *out) {
    const size_t bytes = __riscv_vsetvlmax_e8m1();
    const size_t first = vl < bytes ? vl : bytes;
    const vint16m1_t zero = __riscv_vmv_v_x_i16m1(0, 1);
    const vint8m1_t low = __riscv_vget_v_i8m2_i8m1(values, 0);
    for (size_t i = 0; i < first; i += 16) {
        const vint8m1_t group = __riscv_vslidedown_vx_i8m1(low, i, 16);
        out[i/16] = __riscv_vmv_x_s_i16m1_i16(__riscv_vwredsum_vs_i8m1_i16m1(group, zero, 16));
    }
    if (vl > bytes) {
        const vint8m1_t high = __riscv_vget_v_i8m2_i8m1(values, 1);
        for (size_t i = 0; i < vl-bytes; i += 16) {
            const vint8m1_t group = __riscv_vslidedown_vx_i8m1(high, i, 16);
            out[(bytes+i)/16] = __riscv_vmv_x_s_i16m1_i16(__riscv_vwredsum_vs_i8m1_i16m1(group, zero, 16));
        }
    }
}
#endif
