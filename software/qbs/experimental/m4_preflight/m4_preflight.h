#pragma once

#include "q8_K-m4-packed.h"

namespace qbs_experimental_m4_preflight {

inline constexpr int64_t max_k = 6144;
inline constexpr uint32_t producer_tag = 4;
struct maxima {
    uint32_t signed_bits[max_k / 256][4];
};
static_assert(sizeof(maxima) == 384, "bounded preflight metadata");

#if GGML_RISCV_Q8_K_M4_VECTOR
// Metadata is private scratch. A false result permits no use of its contents.
template <size_t MaxAVL = 32>
inline bool preflight(const float *x, int64_t k, maxima &result) {
    static_assert(MaxAVL > 0 && MaxAVL <= 256, "invalid preflight AVL");
    if (k <= 0 || k > max_k || k % 256) return false;
    const size_t span = __riscv_vsetvl_e32m1(MaxAVL);
    for (int64_t b = 0; b < k / 256; ++b) {
        for (int row = 0; row < 4; ++row) {
            auto maximum = __riscv_vmv_v_x_u32m1(0, span);
            auto minimum_minus_one = __riscv_vmv_v_x_u32m1(UINT32_MAX, span);
            auto positions = __riscv_vmv_v_x_u32m1(UINT32_MAX, span);
            for (size_t offset = 0; offset < 256;) {
                const size_t vl = __riscv_vsetvl_e32m1(
                    256 - offset < span ? 256 - offset : span);
                const auto input = __riscv_vle32_v_f32m1(x + row*k + b*256 + offset, vl);
                const auto bits = __riscv_vreinterpret_v_f32m1_u32m1(input);
                const auto absolute = __riscv_vand_vx_u32m1(bits, UINT32_C(0x7fffffff), vl);
                const auto newer = __riscv_vmsgtu_vv_u32m1_b32(absolute, maximum, vl);
                const auto ordinal = __riscv_vadd_vx_u32m1(__riscv_vid_v_u32m1(vl), offset, vl);
                positions = __riscv_vmerge_vvm_u32m1_tu(positions, positions, ordinal, newer, vl);
                maximum = __riscv_vmaxu_vv_u32m1_tu(maximum, maximum, absolute, vl);
                const auto minus_one = __riscv_vsub_vx_u32m1(absolute, 1, vl);
                minimum_minus_one = __riscv_vminu_vv_u32m1_tu(
                    minimum_minus_one, minimum_minus_one, minus_one, vl);
                offset += vl;
            }
            const auto zero = __riscv_vmv_v_x_u32m1(0, 1);
            const auto ones = __riscv_vmv_v_x_u32m1(UINT32_MAX, 1);
            const uint32_t max_bits = __riscv_vmv_x_s_u32m1_u32(
                __riscv_vredmaxu_vs_u32m1_u32m1(maximum, zero, span));
            const uint32_t min_minus_one = __riscv_vmv_x_s_u32m1_u32(
                __riscv_vredminu_vs_u32m1_u32m1(minimum_minus_one, ones, span));
            if (min_minus_one < UINT32_C(0x007fffff) ||
                (max_bits && (max_bits < UINT32_C(0x08800000) ||
                              max_bits > UINT32_C(0x77000000)))) return false;
            result.signed_bits[b][row] = 0;
            if (max_bits) {
                // Lane order is not input order after more than one vector chunk.
                const auto matches = __riscv_vmseq_vx_u32m1_b32(maximum, max_bits, span);
                const auto absent = __riscv_vmv_v_x_u32m1(UINT32_MAX, span);
                const auto candidates = __riscv_vmerge_vvm_u32m1(absent, positions, matches, span);
                const uint32_t first = __riscv_vmv_x_s_u32m1_u32(
                    __riscv_vredminu_vs_u32m1_u32m1(candidates, ones, span));
                std::memcpy(&result.signed_bits[b][row], x + row*k + b*256 + first, sizeof(uint32_t));
            }
        }
    }
    return true;
}
#endif

// Same input/output and bool contract as the accepted packed parallel producer.
inline bool quantize(const float *GGML_RESTRICT x, void *GGML_RESTRICT output, int64_t k) {
    namespace old = ggml_riscv_q8_K_m4_packed;
    assert(k >= 0 && k % QK_K == 0 && k / QK_K <= INT_MAX);
#if GGML_RISCV_Q8_K_M4_VECTOR && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
    if (k > 0 && k <= max_k) {
        unsigned frm;
        asm volatile("frrm %0" : "=r"(frm) :: "memory");
        const size_t span = __riscv_vsetvl_e32m4(128);
        maxima retained;
        if (!frm && span >= 16 && span % 16 == 0 && preflight(x, k, retained)) {
            auto *y = static_cast<block_q8_Kx4 *>(output);
            for (int64_t b = 0; b < k / QK_K; ++b) {
                float scale[4];
                for (int row = 0; row < 4; ++row) {
                    float maximum;
                    const uint32_t bits = retained.signed_bits[b][row];
                    std::memcpy(&maximum, &bits, sizeof(maximum));
                    const bool nonzero = (bits & UINT32_C(0x7fffffff)) != 0;
                    scale[row] = nonzero ? -127.0f / maximum : 0.0f;
                    y[b].d[row] = nonzero ? 1.0f / scale[row] : 0.0f;
                }
                for (size_t first = 0; first < QK_K; first += span) {
                    const size_t vl = __riscv_vsetvl_e32m4(span);
                    const auto q0 = old::encode(x + b*QK_K + first, scale[0], vl);
                    old::sums<true>(q0, y[b].bsums + 4*(first/16), vl);
                    const auto q1 = old::encode(x + k + b*QK_K + first, scale[1], vl);
                    old::sums<true>(q1, y[b].bsums + 4*(first/16) + 1, vl);
                    const auto q2 = old::encode(x + 2*k + b*QK_K + first, scale[2], vl);
                    old::sums<true>(q2, y[b].bsums + 4*(first/16) + 2, vl);
                    const auto q3 = old::encode(x + 3*k + b*QK_K + first, scale[3], vl);
                    old::sums<true>(q3, y[b].bsums + 4*(first/16) + 3, vl);
                    old::store(y[b].qs + 4*first, q0, q1, q2, q3, vl);
                }
            }
            return true;
        }
    }
#endif
    return old::quantize<true>(x, output, k);
}

} // namespace qbs_experimental_m4_preflight
