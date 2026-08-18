#include "repack_kernels.h"

#include <riscv_vector.h>

// Reuse the exact upstream-style single-output implementation already used by
// the standalone llama.cpp microkernel harness.
#include "../llama_q4km_micro/micro_kernels.c"

float q4k_dot_original(const block_q4_K *weight,
                       const block_q8_K *activation, int n) {
  return q4km_vec_dot_q4_K_q8_K(weight, activation, n);
}

float q4k_dot_vl1024(const block_q4_K *x, const block_q8_K *y, int n) {
  const int blocks = n / QK_K;
  static const uint32_t mask1 = 0x3f3f3f3fu;
  static const uint32_t mask2 = 0x0f0f0f0fu;
  static const uint32_t mask3 = 0x03030303u;
  float result = 0.0f;

  for (int block = 0; block < blocks; ++block) {
    uint32_t temporary[4];
    memcpy(temporary, x[block].scales, 12);
    temporary[3] = ((temporary[2] >> 4) & mask2) |
                   (((temporary[1] >> 6) & mask3) << 4);
    const uint32_t auxiliary = temporary[1] & mask1;
    temporary[1] = (temporary[2] & mask2) |
                   (((temporary[0] >> 6) & mask3) << 4);
    temporary[2] = auxiliary;
    temporary[0] &= mask1;
    const uint8_t *scales = (const uint8_t *)&temporary[0];
    const uint8_t *mins = (const uint8_t *)&temporary[2];
    const float d = y[block].d * fp16_to_fp32(x[block].d);
    const float dmin = y[block].d * fp16_to_fp32(x[block].dmin);

    const size_t vl8 = 8;
    const vint16mf2_t sums0 =
        __riscv_vlse16_v_i16mf2(y[block].bsums, 4, vl8);
    const vint16mf2_t sums1 =
        __riscv_vlse16_v_i16mf2(y[block].bsums + 1, 4, vl8);
    const vint16mf2_t sums = __riscv_vadd_vv_i16mf2(sums0, sums1, vl8);
    const vuint8mf4_t mins8 = __riscv_vle8_v_u8mf4(mins, vl8);
    const vint16mf2_t extended_mins =
        __riscv_vreinterpret_v_u16mf2_i16mf2(
            __riscv_vzext_vf2_u16mf2(mins8, vl8));
    const vint32m1_t min_products =
        __riscv_vwmul_vv_i32m1(sums, extended_mins, vl8);
    const vint32m1_t min_sum = __riscv_vredsum_vs_i32m1_i32m1(
        min_products, __riscv_vmv_v_x_i32m1(0, 1), vl8);
    result -= dmin * (float)__riscv_vmv_x_s_i32m1_i32(min_sum);

    const uint8_t *q4 = x[block].qs;
    const int8_t *q8 = y[block].qs;
    const size_t vl32 = 32;
    vint32m1_t lower_acc = __riscv_vmv_v_x_i32m1(0, vl32);
    vint32m1_t upper_acc = __riscv_vmv_v_x_i32m1(0, vl32);

    for (int group = 0; group < QK_K / 64; ++group) {
      const vuint8mf4_t packed = __riscv_vle8_v_u8mf4(q4, vl32);
      const vint8mf4_t q4_lower = __riscv_vreinterpret_v_u8mf4_i8mf4(
          __riscv_vand_vx_u8mf4(packed, 0x0f, vl32));
      const vint8mf4_t q4_upper = __riscv_vreinterpret_v_u8mf4_i8mf4(
          __riscv_vsrl_vx_u8mf4(packed, 4, vl32));
      const vint16mf2_t lower_products = __riscv_vwmul_vv_i16mf2(
          q4_lower, __riscv_vle8_v_i8mf4(q8, vl32), vl32);
      const vint16mf2_t upper_products = __riscv_vwmul_vv_i16mf2(
          q4_upper, __riscv_vle8_v_i8mf4(q8 + 32, vl32), vl32);
      lower_acc = __riscv_vwmacc_vx_i32m1(
          lower_acc, scales[2 * group], lower_products, vl32);
      upper_acc = __riscv_vwmacc_vx_i32m1(
          upper_acc, scales[2 * group + 1], upper_products, vl32);
      q4 += 32;
      q8 += 64;
    }

    const vint32m1_t dot_acc =
        __riscv_vadd_vv_i32m1(lower_acc, upper_acc, vl32);
    const vint32m1_t dot_sum = __riscv_vredsum_vs_i32m1_i32m1(
        dot_acc, __riscv_vmv_v_x_i32m1(0, 1), vl32);
    result += d * (float)__riscv_vmv_x_s_i32m1_i32(dot_sum);
  }
  return result;
}

static inline vuint8mf4_t q4k_scale32(
    const block_q4_Kx32_ara *block, int sub_block, size_t vl) {
  if (sub_block < 4) {
    return __riscv_vand_vx_u8mf4(
        __riscv_vle8_v_u8mf4(block->scales + sub_block * 32, vl),
        0x3f, vl);
  }
  const vuint8mf4_t low = __riscv_vle8_v_u8mf4(
      block->scales + (sub_block + 4) * 32, vl);
  const vuint8mf4_t high = __riscv_vle8_v_u8mf4(
      block->scales + (sub_block - 4) * 32, vl);
  return __riscv_vor_vv_u8mf4(
      __riscv_vand_vx_u8mf4(low, 0x0f, vl),
      __riscv_vsll_vx_u8mf4(__riscv_vsrl_vx_u8mf4(high, 6, vl), 4, vl), vl);
}

static inline vuint8mf4_t q4k_min32(
    const block_q4_Kx32_ara *block, int sub_block, size_t vl) {
  if (sub_block < 4) {
    return __riscv_vand_vx_u8mf4(
        __riscv_vle8_v_u8mf4(block->scales + (sub_block + 4) * 32, vl),
        0x3f, vl);
  }
  const vuint8mf4_t low = __riscv_vle8_v_u8mf4(
      block->scales + (sub_block + 4) * 32, vl);
  const vuint8mf4_t high = __riscv_vle8_v_u8mf4(
      block->scales + sub_block * 32, vl);
  return __riscv_vor_vv_u8mf4(
      __riscv_vsrl_vx_u8mf4(low, 4, vl),
      __riscv_vsll_vx_u8mf4(__riscv_vsrl_vx_u8mf4(high, 6, vl), 4, vl), vl);
}

static inline vfloat32m1_t load_weight_scale(const ggml_half *source,
                                              size_t vl) {
  const vfloat16mf2_t packed = __riscv_vle16_v_f16mf2(
      (const _Float16 *)source, vl);
  return __riscv_vfwcvt_f_f_v_f32m1(packed, vl);
}

void q4k_gemv_32(const block_q4_Kx32_ara *weights,
                 const block_q8_K *activation, float *output, int n) {
  const int blocks = n / QK_K;
  const size_t vl = __riscv_vsetvl_e32m1(Q4K_BENCH_ROWS);
  vfloat32m1_t sumf = __riscv_vfmv_v_f_f32m1(0.0f, vl);

  for (int block = 0; block < blocks; ++block) {
    vint32m1_t dot = __riscv_vmv_v_x_i32m1(0, vl);
    vint32m1_t min_correction = __riscv_vmv_v_x_i32m1(0, vl);

    for (int sub_block = 0; sub_block < 8; ++sub_block) {
      const vint16mf2_t min = __riscv_vreinterpret_v_u16mf2_i16mf2(
          __riscv_vzext_vf2_u16mf2(
              q4k_min32(&weights[block], sub_block, vl), vl));
      const int16_t bsum = activation[block].bsums[2 * sub_block] +
                           activation[block].bsums[2 * sub_block + 1];
      min_correction =
          __riscv_vwmacc_vx_i32m1(min_correction, bsum, min, vl);
    }

    for (int pair = 0; pair < 4; ++pair) {
      const vint16mf2_t scale_low = __riscv_vreinterpret_v_u16mf2_i16mf2(
          __riscv_vzext_vf2_u16mf2(q4k_scale32(&weights[block], 2 * pair, vl), vl));
      const vint16mf2_t scale_high = __riscv_vreinterpret_v_u16mf2_i16mf2(
          __riscv_vzext_vf2_u16mf2(q4k_scale32(&weights[block], 2 * pair + 1, vl), vl));

      for (int half = 0; half < 2; ++half) {
        vint16mf2_t partial_low = __riscv_vmv_v_x_i16mf2(0, vl);
        vint16mf2_t partial_high = __riscv_vmv_v_x_i16mf2(0, vl);
        for (int i = half * 16; i < (half + 1) * 16; ++i) {
          const vuint8mf4_t packed = __riscv_vle8_v_u8mf4(
              weights[block].qs + (pair * 32 + i) * Q4K_BENCH_ROWS, vl);
          const vint8mf4_t q4_low = __riscv_vreinterpret_v_u8mf4_i8mf4(
              __riscv_vand_vx_u8mf4(packed, 0x0f, vl));
          const vint8mf4_t q4_high = __riscv_vreinterpret_v_u8mf4_i8mf4(
              __riscv_vsrl_vx_u8mf4(packed, 4, vl));
          partial_low = __riscv_vwmacc_vx_i16mf2(
              partial_low, activation[block].qs[pair * 64 + i], q4_low, vl);
          partial_high = __riscv_vwmacc_vx_i16mf2(
              partial_high, activation[block].qs[pair * 64 + 32 + i], q4_high, vl);
        }
        dot = __riscv_vwmacc_vv_i32m1(dot, scale_low, partial_low, vl);
        dot = __riscv_vwmacc_vv_i32m1(dot, scale_high, partial_high, vl);
      }
    }

    const vfloat32m1_t weight_scale = load_weight_scale(weights[block].d, vl);
    const vfloat32m1_t weight_min = load_weight_scale(weights[block].dmin, vl);
    const vfloat32m1_t dot_f = __riscv_vfcvt_f_x_v_f32m1(dot, vl);
    const vfloat32m1_t min_f = __riscv_vfcvt_f_x_v_f32m1(min_correction, vl);
    const vfloat32m1_t scaled_d =
        __riscv_vfmul_vf_f32m1(weight_scale, activation[block].d, vl);
    const vfloat32m1_t scaled_min =
        __riscv_vfmul_vf_f32m1(weight_min, activation[block].d, vl);
    sumf = __riscv_vfmacc_vv_f32m1(sumf, dot_f, scaled_d, vl);
    sumf = __riscv_vfsub_vv_f32m1(
        sumf, __riscv_vfmul_vv_f32m1(min_f, scaled_min, vl), vl);
  }
  __riscv_vse32_v_f32m1(output, sumf, vl);
}

void q4k_gemm_32x4(const block_q4_Kx32_ara *weights,
                   const block_q8_Kx4 *activation, float *output, int n) {
  const int blocks = n / QK_K;
  const size_t vl = __riscv_vsetvl_e32m1(Q4K_BENCH_ROWS);
  vfloat32m1_t sumf0 = __riscv_vfmv_v_f_f32m1(0.0f, vl);
  vfloat32m1_t sumf1 = __riscv_vfmv_v_f_f32m1(0.0f, vl);
  vfloat32m1_t sumf2 = __riscv_vfmv_v_f_f32m1(0.0f, vl);
  vfloat32m1_t sumf3 = __riscv_vfmv_v_f_f32m1(0.0f, vl);

  for (int block = 0; block < blocks; ++block) {
    vint32m1_t dot0 = __riscv_vmv_v_x_i32m1(0, vl);
    vint32m1_t dot1 = __riscv_vmv_v_x_i32m1(0, vl);
    vint32m1_t dot2 = __riscv_vmv_v_x_i32m1(0, vl);
    vint32m1_t dot3 = __riscv_vmv_v_x_i32m1(0, vl);
    vint32m1_t min0 = __riscv_vmv_v_x_i32m1(0, vl);
    vint32m1_t min1 = __riscv_vmv_v_x_i32m1(0, vl);
    vint32m1_t min2 = __riscv_vmv_v_x_i32m1(0, vl);
    vint32m1_t min3 = __riscv_vmv_v_x_i32m1(0, vl);

    for (int sub_block = 0; sub_block < 8; ++sub_block) {
      const vint16mf2_t min = __riscv_vreinterpret_v_u16mf2_i16mf2(
          __riscv_vzext_vf2_u16mf2(
              q4k_min32(&weights[block], sub_block, vl), vl));
      const int base = sub_block * 8;
      min0 = __riscv_vwmacc_vx_i32m1(
          min0, activation[block].bsums[base] +
                    activation[block].bsums[base + 4], min, vl);
      min1 = __riscv_vwmacc_vx_i32m1(
          min1, activation[block].bsums[base + 1] +
                    activation[block].bsums[base + 5], min, vl);
      min2 = __riscv_vwmacc_vx_i32m1(
          min2, activation[block].bsums[base + 2] +
                    activation[block].bsums[base + 6], min, vl);
      min3 = __riscv_vwmacc_vx_i32m1(
          min3, activation[block].bsums[base + 3] +
                    activation[block].bsums[base + 7], min, vl);
    }

    for (int pair = 0; pair < 4; ++pair) {
      const vint16mf2_t scale_low = __riscv_vreinterpret_v_u16mf2_i16mf2(
          __riscv_vzext_vf2_u16mf2(q4k_scale32(&weights[block], 2 * pair, vl), vl));
      const vint16mf2_t scale_high = __riscv_vreinterpret_v_u16mf2_i16mf2(
          __riscv_vzext_vf2_u16mf2(q4k_scale32(&weights[block], 2 * pair + 1, vl), vl));
      for (int half = 0; half < 2; ++half) {
        vint16mf2_t low0 = __riscv_vmv_v_x_i16mf2(0, vl);
        vint16mf2_t low1 = __riscv_vmv_v_x_i16mf2(0, vl);
        vint16mf2_t low2 = __riscv_vmv_v_x_i16mf2(0, vl);
        vint16mf2_t low3 = __riscv_vmv_v_x_i16mf2(0, vl);
        vint16mf2_t high0 = __riscv_vmv_v_x_i16mf2(0, vl);
        vint16mf2_t high1 = __riscv_vmv_v_x_i16mf2(0, vl);
        vint16mf2_t high2 = __riscv_vmv_v_x_i16mf2(0, vl);
        vint16mf2_t high3 = __riscv_vmv_v_x_i16mf2(0, vl);
        for (int i = half * 16; i < (half + 1) * 16; ++i) {
          const vuint8mf4_t packed = __riscv_vle8_v_u8mf4(
              weights[block].qs + (pair * 32 + i) * Q4K_BENCH_ROWS, vl);
          const vint8mf4_t q4_low = __riscv_vreinterpret_v_u8mf4_i8mf4(
              __riscv_vand_vx_u8mf4(packed, 0x0f, vl));
          const vint8mf4_t q4_high = __riscv_vreinterpret_v_u8mf4_i8mf4(
              __riscv_vsrl_vx_u8mf4(packed, 4, vl));
          const int q8_low = pair * 256 + i * 4;
          const int q8_high = q8_low + 128;
          low0 = __riscv_vwmacc_vx_i16mf2(
              low0, activation[block].qs[q8_low], q4_low, vl);
          low1 = __riscv_vwmacc_vx_i16mf2(
              low1, activation[block].qs[q8_low + 1], q4_low, vl);
          low2 = __riscv_vwmacc_vx_i16mf2(
              low2, activation[block].qs[q8_low + 2], q4_low, vl);
          low3 = __riscv_vwmacc_vx_i16mf2(
              low3, activation[block].qs[q8_low + 3], q4_low, vl);
          high0 = __riscv_vwmacc_vx_i16mf2(
              high0, activation[block].qs[q8_high], q4_high, vl);
          high1 = __riscv_vwmacc_vx_i16mf2(
              high1, activation[block].qs[q8_high + 1], q4_high, vl);
          high2 = __riscv_vwmacc_vx_i16mf2(
              high2, activation[block].qs[q8_high + 2], q4_high, vl);
          high3 = __riscv_vwmacc_vx_i16mf2(
              high3, activation[block].qs[q8_high + 3], q4_high, vl);
        }
        dot0 = __riscv_vwmacc_vv_i32m1(dot0, scale_low, low0, vl);
        dot1 = __riscv_vwmacc_vv_i32m1(dot1, scale_low, low1, vl);
        dot2 = __riscv_vwmacc_vv_i32m1(dot2, scale_low, low2, vl);
        dot3 = __riscv_vwmacc_vv_i32m1(dot3, scale_low, low3, vl);
        dot0 = __riscv_vwmacc_vv_i32m1(dot0, scale_high, high0, vl);
        dot1 = __riscv_vwmacc_vv_i32m1(dot1, scale_high, high1, vl);
        dot2 = __riscv_vwmacc_vv_i32m1(dot2, scale_high, high2, vl);
        dot3 = __riscv_vwmacc_vv_i32m1(dot3, scale_high, high3, vl);
      }
    }

    const vfloat32m1_t weight_scale = load_weight_scale(weights[block].d, vl);
    const vfloat32m1_t weight_min = load_weight_scale(weights[block].dmin, vl);
    const vfloat32m1_t dotf0 = __riscv_vfcvt_f_x_v_f32m1(dot0, vl);
    const vfloat32m1_t dotf1 = __riscv_vfcvt_f_x_v_f32m1(dot1, vl);
    const vfloat32m1_t dotf2 = __riscv_vfcvt_f_x_v_f32m1(dot2, vl);
    const vfloat32m1_t dotf3 = __riscv_vfcvt_f_x_v_f32m1(dot3, vl);
    const vfloat32m1_t minf0 = __riscv_vfcvt_f_x_v_f32m1(min0, vl);
    const vfloat32m1_t minf1 = __riscv_vfcvt_f_x_v_f32m1(min1, vl);
    const vfloat32m1_t minf2 = __riscv_vfcvt_f_x_v_f32m1(min2, vl);
    const vfloat32m1_t minf3 = __riscv_vfcvt_f_x_v_f32m1(min3, vl);
    const vfloat32m1_t scale0 = __riscv_vfmul_vf_f32m1(
        weight_scale, activation[block].d[0], vl);
    const vfloat32m1_t scale1 = __riscv_vfmul_vf_f32m1(
        weight_scale, activation[block].d[1], vl);
    const vfloat32m1_t scale2 = __riscv_vfmul_vf_f32m1(
        weight_scale, activation[block].d[2], vl);
    const vfloat32m1_t scale3 = __riscv_vfmul_vf_f32m1(
        weight_scale, activation[block].d[3], vl);
    const vfloat32m1_t dmin0 = __riscv_vfmul_vf_f32m1(
        weight_min, activation[block].d[0], vl);
    const vfloat32m1_t dmin1 = __riscv_vfmul_vf_f32m1(
        weight_min, activation[block].d[1], vl);
    const vfloat32m1_t dmin2 = __riscv_vfmul_vf_f32m1(
        weight_min, activation[block].d[2], vl);
    const vfloat32m1_t dmin3 = __riscv_vfmul_vf_f32m1(
        weight_min, activation[block].d[3], vl);
    sumf0 = __riscv_vfmacc_vv_f32m1(sumf0, dotf0, scale0, vl);
    sumf1 = __riscv_vfmacc_vv_f32m1(sumf1, dotf1, scale1, vl);
    sumf2 = __riscv_vfmacc_vv_f32m1(sumf2, dotf2, scale2, vl);
    sumf3 = __riscv_vfmacc_vv_f32m1(sumf3, dotf3, scale3, vl);
    sumf0 = __riscv_vfsub_vv_f32m1(
        sumf0, __riscv_vfmul_vv_f32m1(minf0, dmin0, vl), vl);
    sumf1 = __riscv_vfsub_vv_f32m1(
        sumf1, __riscv_vfmul_vv_f32m1(minf1, dmin1, vl), vl);
    sumf2 = __riscv_vfsub_vv_f32m1(
        sumf2, __riscv_vfmul_vv_f32m1(minf2, dmin2, vl), vl);
    sumf3 = __riscv_vfsub_vv_f32m1(
        sumf3, __riscv_vfmul_vv_f32m1(minf3, dmin3, vl), vl);
  }

  __riscv_vse32_v_f32m1(output, sumf0, vl);
  __riscv_vse32_v_f32m1(output + Q4K_BENCH_ROWS, sumf1, vl);
  __riscv_vse32_v_f32m1(output + 2 * Q4K_BENCH_ROWS, sumf2, vl);
  __riscv_vse32_v_f32m1(output + 3 * Q4K_BENCH_ROWS, sumf3, vl);
}
