#pragma once

// Isolated candidate. Not selected by production GGML.
// Match the pinned production M4 generic's contracted bias-add rounding,
// not q8_0's roundf. Revalidate contraction when the production compiler changes.
#if !defined(__riscv_vector) || defined(__FAST_MATH__) || \
    (defined(__FINITE_MATH_ONLY__) && __FINITE_MATH_ONLY__)
#error "Requires RVV and strict floating-point compilation"
#endif
#include "ggml-impl.h"
#include "simd-mappings.h"
#include "arch-fallback.h"
#include "repack.h"
#include <cassert>
#include <climits>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <riscv_vector.h>

namespace qbs_q8k_m4_prepare_candidate {

inline bool vector_domain(const float * x, int64_t k) {
    for (int64_t b = 0; b < k / QK_K; ++b) {
        for (int row = 0; row < 4; ++row) {
            uint32_t maximum = 0;
            for (int j = 0; j < QK_K; ++j) {
                uint32_t bits;
                std::memcpy(&bits, x + row * k + b * QK_K + j, sizeof(bits));
                bits &= 0x7fffffffU;
                if (bits >= 0x7f800000U || (bits && bits < 0x00800000U)) return false;
                if (bits > maximum) maximum = bits;
            }
            // Conservatively bound both scale divisions to normal finite values.
            if (maximum && (maximum < 0x08800000U || maximum > 0x77000000U)) return false;
        }
    }
    return true;
}

template <size_t MaxAVL = 16>
inline bool quantize(const float * GGML_RESTRICT x, void * GGML_RESTRICT vy, int64_t k) {
    static_assert(MaxAVL > 0 && MaxAVL <= 16, "invalid AVL cap");
    static_assert(QK_K == 256, "native block layout changed");
    assert(k >= 0 && k % QK_K == 0 && k / QK_K <= INT_MAX);
    unsigned frm;
    asm volatile("frrm %0" : "=r"(frm) : : "memory");
    if (frm != 0 || k == 0 || !vector_domain(x, k)) {
        ggml_quantize_mat_q8_K_4x1_ara_generic(x, vy, k);
        return false;
    }
    auto * y = static_cast<block_q8_Kx4 *>(vy);
    for (int64_t b = 0; b < k / QK_K; ++b) {
        float scales[4];
        for (int row = 0; row < 4; ++row) {
            float amax = 0.0f, maximum = 0.0f;
            for (int j = 0; j < QK_K; ++j) {
                const float value = x[row * k + b * QK_K + j];
                // Strict comparison keeps the FIRST signed maximum on ties.
                if (amax < fabsf(value)) { amax = fabsf(value); maximum = value; }
            }
            scales[row] = amax ? -127.0f / maximum : 0.0f;
            y[b].d[row] = amax ? 1.0f / scales[row] : 0.0f;
        }
        for (int row = 0; row < 4; ++row) {
            for (int group = 0; group < QK_K / 16; ++group) {
                int sum = 0;
                for (size_t offset = 0; offset < 16;) {
                    const size_t remaining = 16 - offset;
                    const size_t vl = __riscv_vsetvl_e32m1(remaining < MaxAVL ? remaining : MaxAVL);
                    const size_t element = group * 16 + offset;
                    const auto input = __riscv_vle32_v_f32m1(x + row*k + b*QK_K + element, vl);
                    const auto bias = __riscv_vfmv_v_f_f32m1(12582912.0f, vl);
                    // The actual linked generic emits fmadd.s here. Explicit
                    // FMA preserves its single rounding and exception flags.
                    const auto biased = __riscv_vfmacc_vf_f32m1(bias, scales[row], input, vl);
                    auto bits = __riscv_vreinterpret_v_f32m1_i32m1(biased);
                    bits = __riscv_vand_vx_i32m1(bits, 0x007fffff, vl);
                    bits = __riscv_vsub_vx_i32m1(bits, 0x00400000, vl);
                    const auto q16 = __riscv_vncvt_x_x_w_i16mf2(bits, vl);
                    const auto q8 = __riscv_vncvt_x_x_w_i8mf4(q16, vl);
                    __riscv_vsse8_v_i8mf4(y[b].qs + 4*element + row, 4, q8, vl);
                    const auto zero = __riscv_vmv_v_x_i16m1(0, 1);
                    const auto subtotal = __riscv_vwredsum_vs_i8mf4_i16m1(q8, zero, vl);
                    sum += __riscv_vmv_x_s_i16m1_i16(subtotal);
                    offset += vl;
                }
                y[b].bsums[group*4 + row] = static_cast<int16_t>(sum);
            }
        }
    }
    return true;
}
} // namespace qbs_q8k_m4_prepare_candidate
