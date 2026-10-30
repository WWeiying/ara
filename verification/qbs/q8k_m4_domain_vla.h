#pragma once

#include <cstddef>
#include <cstdint>
#include <riscv_vector.h>

// Successor preflight only. The sealed running quantizer is not changed.
// Float loads/reinterpretation do not perform floating-point arithmetic.
namespace qbs_q8k_m4_domain_vla {

template <size_t MaxAVL = 32>
inline bool check(const float * x, int64_t k) {
    static_assert(MaxAVL > 0, "invalid AVL cap");
    constexpr size_t block = 256;
    const size_t span = __riscv_vsetvl_e32m1(MaxAVL < block ? MaxAVL : block);
    for (int64_t b = 0; b < k / int64_t(block); ++b) {
        for (int row = 0; row < 4; ++row) {
            auto maximum = __riscv_vmv_v_x_u32m1(0, span);
            auto minimum_minus_one = __riscv_vmv_v_x_u32m1(UINT32_MAX, span);
            for (size_t offset = 0; offset < block;) {
                const size_t remaining = block - offset;
                const size_t vl = __riscv_vsetvl_e32m1(remaining < span ? remaining : span);
                const auto input = __riscv_vle32_v_f32m1(x + row*k + b*block + offset, vl);
                const auto bits = __riscv_vreinterpret_v_f32m1_u32m1(input);
                const auto absolute = __riscv_vand_vx_u32m1(bits, UINT32_C(0x7fffffff), vl);
                const auto minus_one = __riscv_vsub_vx_u32m1(absolute, 1, vl);
                // A short final chunk must preserve accumulated high elements.
                maximum = __riscv_vmaxu_vv_u32m1_tu(maximum, maximum, absolute, vl);
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
            // Zero wraps to UINT32_MAX. Exactly the nonzero subnormal range
            // maps below 0x007fffff. The upper bound also rejects Inf/NaN.
            if (min_minus_one < UINT32_C(0x007fffff) ||
                (max_bits && (max_bits < UINT32_C(0x08800000) ||
                              max_bits > UINT32_C(0x77000000)))) return false;
        }
    }
    return true;
}

} // namespace qbs_q8k_m4_domain_vla
