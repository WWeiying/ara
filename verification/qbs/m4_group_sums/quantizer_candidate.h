#pragma once

#include "q8_K-m4.h"
#include "candidate.h"
#include <cstdlib>
#include <cstring>

namespace qbs_m4_parallel_sums {

#if GGML_RISCV_Q8_K_M4_VECTOR
inline vint8m1_t encode(const float *input, float scale, size_t vl) {
    const auto x = __riscv_vle32_v_f32m4(input, vl);
    const auto bias = __riscv_vfmv_v_f_f32m4(12582912.0f, vl);
    const auto biased = __riscv_vfmacc_vf_f32m4(bias, scale, x, vl);
    auto bits = __riscv_vreinterpret_v_f32m4_i32m4(biased);
    bits = __riscv_vand_vx_i32m4(bits, 0x007fffff, vl);
    bits = __riscv_vsub_vx_i32m4(bits, 0x00400000, vl);
    return __riscv_vncvt_x_x_w_i8m1(__riscv_vncvt_x_x_w_i16m2(bits, vl), vl);
}

inline void sums(vint8m1_t q, int16_t *destination, size_t vl) {
    qbs_m4_group_sums(q,destination,vl);
}

// Qualified for GNU/Clang's alias extension and the existing aligned payload.
// Zero extension preserves each signed byte's bits without polluting its peers.
typedef uint32_t alias_word __attribute__((__may_alias__));
inline vuint32m4_t widen(vint8m1_t q, size_t vl) {
    return __riscv_vzext_vf4_u32m4(__riscv_vreinterpret_v_i8m1_u8m1(q), vl);
}
inline void store(int8_t *destination, vint8m1_t q0, vint8m1_t q1,
                  vint8m1_t q2, vint8m1_t q3, size_t vl) {
    auto words = widen(q0, vl);
    words = __riscv_vor_vv_u32m4(words, __riscv_vsll_vx_u32m4(widen(q1, vl), 8, vl), vl);
    words = __riscv_vor_vv_u32m4(words, __riscv_vsll_vx_u32m4(widen(q2, vl), 16, vl), vl);
    words = __riscv_vor_vv_u32m4(words, __riscv_vsll_vx_u32m4(widen(q3, vl), 24, vl), vl);
    __riscv_vse32_v_u32m4(reinterpret_cast<alias_word *>(destination), words, vl);
}
#endif

// Four contiguous F32 rows, K divisible by 256, disjoint aligned buffers.
// False means the generic fallback has already produced the complete output.
inline bool quantize(const float *GGML_RESTRICT x, void *GGML_RESTRICT output, int64_t k) {
    static_assert(QK_K == 256, "native block layout changed");
    assert(k >= 0 && k % QK_K == 0 && k / QK_K <= INT_MAX);
#if GGML_RISCV_Q8_K_M4_VECTOR && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
    static_assert(offsetof(block_q8_Kx4, qs) % 4 == 0 && sizeof(block_q8_Kx4) % 4 == 0,
                  "unaligned word payload");
    unsigned frm;
    asm volatile("frrm %0" : "=r"(frm) :: "memory");
    const size_t span = __riscv_vsetvl_e32m4(128);
    if (frm || !k || span < 16 || span % 16 || !ggml_riscv_q8_K_m4::vector_domain(x, k)) {
        ggml_quantize_mat_q8_K_4x1_ara_generic(x, output, k);
        return false;
    }
    auto *y = static_cast<block_q8_Kx4 *>(output);
    for (int64_t b = 0; b < k / QK_K; ++b) {
        float scale[4];
        for (int row = 0; row < 4; ++row) {
            float absolute;
            const float maximum = ggml_riscv_q8_K_signed_max(x + row*k + b*QK_K, QK_K, &absolute);
            scale[row] = absolute ? -127.0f / maximum : 0.0f;
            y[b].d[row] = absolute ? 1.0f / scale[row] : 0.0f;
        }
        for (size_t first = 0; first < QK_K; first += span) {
            const size_t vl = __riscv_vsetvl_e32m4(span);
            const auto q0 = encode(x + b*QK_K + first, scale[0], vl);
            sums(q0, y[b].bsums + 4*(first/16), vl);
            const auto q1 = encode(x + k + b*QK_K + first, scale[1], vl);
            sums(q1, y[b].bsums + 4*(first/16) + 1, vl);
            const auto q2 = encode(x + 2*k + b*QK_K + first, scale[2], vl);
            sums(q2, y[b].bsums + 4*(first/16) + 2, vl);
            const auto q3 = encode(x + 3*k + b*QK_K + first, scale[3], vl);
            sums(q3, y[b].bsums + 4*(first/16) + 3, vl);
            store(y[b].qs + 4*first, q0, q1, q2, q3, vl);
        }
    }
    return true;
#else
    ggml_quantize_mat_q8_K_4x1_ara_generic(x, output, k);
    return false;
#endif
}

// The selector is process-stable, like the existing runtime feature switches.
// Keep disabled unless the caller has enabled the M4 preparation path as well.
inline bool enabled() {
    static const bool value = [] {
        const char *s = std::getenv("GGML_RISCV_QBS_M4_PACKED");
        return s && std::strcmp(s, "1") == 0;
    }();
    return value;
}

inline uint32_t producer_tag() { return enabled() ? 2u : 1u; }

inline bool selected_quantize(const float *x, void *output, int64_t k) {
    return enabled() ? quantize(x, output, k) : ggml_riscv_q8_K_m4::quantize<16>(x, output, k);
}

} // namespace ggml_riscv_q8_K_m4_packed
