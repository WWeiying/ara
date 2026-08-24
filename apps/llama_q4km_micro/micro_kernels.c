#include "micro_kernels.h"

#include <math.h>
#include <riscv_vector.h>
#include <string.h>

// Ported verbatim in operation order from llama.cpp's RISC-V RVV quant kernels.
// Only GGML dispatch/capture wrappers are omitted by the bare-metal harness.

static float fp16_to_fp32(uint16_t value) {
  _Float16 half;
  memcpy(&half, &value, sizeof(value));
  return (float)half;
}

static uint16_t fp32_to_fp16(float value) {
  const _Float16 half = (_Float16)value;
  uint16_t bits;
  memcpy(&bits, &half, sizeof(bits));
  return bits;
}

void q4km_quantize_row_q8_0(const float *x, block_q8_0 *y, int64_t k) {
  if (k <= 0 || k % QK8_0 != 0) return;
  const int blocks = (int)(k / QK8_0);
  const size_t vl = QK8_0;

  for (int block = 0; block < blocks; ++block) {
    const vfloat32m8_t values =
        __riscv_vle32_v_f32m8(x + block * QK8_0, vl);
    const vfloat32m8_t absolute = __riscv_vfabs_v_f32m8(values, vl);
    const vfloat32m1_t initial = __riscv_vfmv_v_f_f32m1(0.0f, vl);
    const vfloat32m1_t reduced =
        __riscv_vfredmax_vs_f32m8_f32m1(absolute, initial, vl);
    const float maximum = __riscv_vfmv_f_s_f32m1_f32(reduced);
    const float scale = maximum / 127.0f;
    const float inverse = scale != 0.0f ? 1.0f / scale : 0.0f;

    y[block].d = fp32_to_fp16(scale);
    const vfloat32m8_t scaled =
        __riscv_vfmul_vf_f32m8(values, inverse, vl);
    const vint16m4_t i16 = __riscv_vfncvt_x_f_w_i16m4(scaled, vl);
    const vint8m2_t i8 = __riscv_vncvt_x_x_w_i8m2(i16, vl);
    __riscv_vse8_v_i8m2(y[block].qs, i8, vl);
  }
}

void q4km_quantize_row_q8_K(const float *x, block_q8_K *y, int64_t k) {
  const size_t blocks = (size_t)k / QK_K;
  const size_t vlmax = __riscv_vsetvlmax_e32m8();

  for (size_t block = 0; block < blocks; ++block) {
    const float *input = x + block * QK_K;
    block_q8_K *output = y + block;
    vfloat32m8_t maximum = __riscv_vfmv_v_f_f32m8(-__builtin_inff(), vlmax);
    vfloat32m8_t minimum = __riscv_vfmv_v_f_f32m8(__builtin_inff(), vlmax);

    size_t remaining = QK_K;
    size_t offset = 0;
    while (remaining != 0) {
      const size_t vl = __riscv_vsetvl_e32m8(remaining);
      const vfloat32m8_t values = __riscv_vle32_v_f32m8(input + offset, vl);
      maximum = __riscv_vfmax_vv_f32m8(maximum, values, vl);
      minimum = __riscv_vfmin_vv_f32m8(minimum, values, vl);
      remaining -= vl;
      offset += vl;
    }

    const vfloat32m1_t initial_max =
        __riscv_vfmv_s_f_f32m1(-__builtin_inff(), 1);
    const vfloat32m1_t initial_min =
        __riscv_vfmv_s_f_f32m1(__builtin_inff(), 1);
    const vfloat32m1_t reduced_max =
        __riscv_vfredmax_vs_f32m8_f32m1(maximum, initial_max, vlmax);
    const vfloat32m1_t reduced_min =
        __riscv_vfredmin_vs_f32m8_f32m1(minimum, initial_min, vlmax);
    const float max_value = __riscv_vfmv_f_s_f32m1_f32(reduced_max);
    const float min_value = __riscv_vfmv_f_s_f32m1_f32(reduced_min);
    const float abs_max = fabsf(max_value);
    const float abs_min = fabsf(min_value);
    const float amplitude = abs_max > abs_min ? abs_max : abs_min;

    if (amplitude == 0.0f) {
      output->d = 0.0f;
      memset(output->qs, 0, sizeof(output->qs));
      memset(output->bsums, 0, sizeof(output->bsums));
      continue;
    }

    const float scale = -127.0f / (abs_max > abs_min ? max_value : min_value);
    output->d = 1.0f / scale;
    remaining = QK_K;
    offset = 0;
    const vint16m1_t zero_sum = __riscv_vmv_v_x_i16m1(0, 1);
    while (remaining != 0) {
      const size_t vl = __riscv_vsetvl_e32m8(remaining);
      vfloat32m8_t values = __riscv_vle32_v_f32m8(input + offset, vl);
      values = __riscv_vfmul_vf_f32m8(values, scale, vl);
      const vint32m8_t i32 =
          __riscv_vfcvt_x_f_v_i32m8_rm(values, __RISCV_FRM_RNE, vl);
      const vint16m4_t i16 =
          __riscv_vnclip_wx_i16m4(i32, 0, __RISCV_VXRM_RNE, vl);
      const vint8m2_t i8 =
          __riscv_vnclip_wx_i8m2(i16, 0, __RISCV_VXRM_RNE, vl);
      __riscv_vse8_v_i8m2(output->qs + offset, i8, vl);

      int sum_index = (int)(offset / 16);
      vint8m1_t chunk = __riscv_vget_v_i8m2_i8m1(i8, 0);
      vint16m1_t sum = __riscv_vwredsum_vs_i8m1_i16m1(chunk, zero_sum, 16);
      output->bsums[sum_index] = __riscv_vmv_x_s_i16m1_i16(sum);
      vint8m2_t shifted = i8;
      for (size_t item = 16; item < vl; item += 16) {
        shifted = __riscv_vslidedown_vx_i8m2(shifted, 16, vl);
        sum_index = (int)((offset + item) / 16);
        chunk = __riscv_vget_v_i8m2_i8m1(shifted, 0);
        sum = __riscv_vwredsum_vs_i8m1_i16m1(chunk, zero_sum, 16);
        output->bsums[sum_index] = __riscv_vmv_x_s_i16m1_i16(sum);
      }
      remaining -= vl;
      offset += vl;
    }
  }
}

float q4km_vec_dot_q3_K_q8_K(const block_q3_K *x, const block_q8_K *y,
                             int n) {
  if (n <= 0 || n % QK_K != 0) return 0.0f;
  const uint32_t mask1 = 0x03030303u;
  const uint32_t mask2 = 0x0f0f0f0fu;
  const vuint16mf2_t indices = __riscv_vid_v_u16mf2(32);
  const vbool32_t upper_half =
      __riscv_vmsgtu_vx_u16mf2_b32(indices, 15, 32);
  float result = 0.0f;

  for (int block = 0; block < n / QK_K; ++block) {
    uint32_t packed_scales[4];
    uint32_t raw_scales[3];
    memcpy(raw_scales, x[block].scales, sizeof(raw_scales));
    packed_scales[3] = ((raw_scales[1] >> 4) & mask2) |
                       (((raw_scales[2] >> 6) & mask1) << 4);
    packed_scales[2] = ((raw_scales[0] >> 4) & mask2) |
                       (((raw_scales[2] >> 4) & mask1) << 4);
    packed_scales[1] = (raw_scales[1] & mask2) |
                       (((raw_scales[2] >> 2) & mask1) << 4);
    packed_scales[0] = (raw_scales[0] & mask2) |
                       ((raw_scales[2] & mask1) << 4);
    int8_t *scales = (int8_t *)packed_scales;
    for (int index = 0; index < 16; ++index) scales[index] -= 32;

    const uint8_t *low_bits = x[block].qs;
    const uint8_t *high_bits = x[block].hmask;
    const int8_t *activation = y[block].qs;
    const size_t vl = 32;
    uint8_t high_mask = 1;
    const vuint8mf4_t high =
        __riscv_vle8_v_u8mf4(high_bits, vl);
    vint32m1_t accum0 = __riscv_vmv_v_x_i32m1(0, vl);
    vint32m1_t accum1 = __riscv_vmv_v_x_i32m1(0, vl);
    vint32m1_t accum2 = __riscv_vmv_v_x_i32m1(0, vl);
    vint32m1_t accum3 = __riscv_vmv_v_x_i32m1(0, vl);

    for (int group = 0; group < 2; ++group) {
      const vuint8mf4_t packed =
          __riscv_vle8_v_u8mf4(low_bits, vl);
      const vint8mf4_t low0 = __riscv_vreinterpret_v_u8mf4_i8mf4(
          __riscv_vand_vx_u8mf4(packed, 0x03, vl));
      const vint8mf4_t low1 = __riscv_vreinterpret_v_u8mf4_i8mf4(
          __riscv_vand_vx_u8mf4(
              __riscv_vsrl_vx_u8mf4(packed, 2, vl), 0x03, vl));
      const vint8mf4_t low2 = __riscv_vreinterpret_v_u8mf4_i8mf4(
          __riscv_vand_vx_u8mf4(
              __riscv_vsrl_vx_u8mf4(packed, 4, vl), 0x03, vl));
      const vint8mf4_t low3 = __riscv_vreinterpret_v_u8mf4_i8mf4(
          __riscv_vand_vx_u8mf4(
              __riscv_vsrl_vx_u8mf4(packed, 6, vl), 0x03, vl));

      const vbool32_t negative0 = __riscv_vmseq_vx_u8mf4_b32(
          __riscv_vand_vx_u8mf4(high, high_mask, vl), 0, vl);
      high_mask <<= 1;
      const vbool32_t negative1 = __riscv_vmseq_vx_u8mf4_b32(
          __riscv_vand_vx_u8mf4(high, high_mask, vl), 0, vl);
      high_mask <<= 1;
      const vbool32_t negative2 = __riscv_vmseq_vx_u8mf4_b32(
          __riscv_vand_vx_u8mf4(high, high_mask, vl), 0, vl);
      high_mask <<= 1;
      const vbool32_t negative3 = __riscv_vmseq_vx_u8mf4_b32(
          __riscv_vand_vx_u8mf4(high, high_mask, vl), 0, vl);
      high_mask <<= 1;
      const vint8mf4_t quant0 =
          __riscv_vsub_vx_i8mf4_mu(negative0, low0, low0, 4, vl);
      const vint8mf4_t quant1 =
          __riscv_vsub_vx_i8mf4_mu(negative1, low1, low1, 4, vl);
      const vint8mf4_t quant2 =
          __riscv_vsub_vx_i8mf4_mu(negative2, low2, low2, 4, vl);
      const vint8mf4_t quant3 =
          __riscv_vsub_vx_i8mf4_mu(negative3, low3, low3, 4, vl);

      const vint16mf2_t product0 = __riscv_vwmul_vv_i16mf2(
          quant0, __riscv_vle8_v_i8mf4(activation, vl), vl);
      const vint16mf2_t product1 = __riscv_vwmul_vv_i16mf2(
          quant1, __riscv_vle8_v_i8mf4(activation + 32, vl), vl);
      const vint16mf2_t product2 = __riscv_vwmul_vv_i16mf2(
          quant2, __riscv_vle8_v_i8mf4(activation + 64, vl), vl);
      const vint16mf2_t product3 = __riscv_vwmul_vv_i16mf2(
          quant3, __riscv_vle8_v_i8mf4(activation + 96, vl), vl);

      accum0 = __riscv_vwmacc_vx_i32m1(accum0, scales[0], product0, 16);
      accum1 = __riscv_vwmacc_vx_i32m1(accum1, scales[2], product1, 16);
      accum2 = __riscv_vwmacc_vx_i32m1(accum2, scales[4], product2, 16);
      accum3 = __riscv_vwmacc_vx_i32m1(accum3, scales[6], product3, 16);
      accum0 = __riscv_vwmacc_vx_i32m1_m(
          upper_half, accum0, scales[1], product0, vl);
      accum1 = __riscv_vwmacc_vx_i32m1_m(
          upper_half, accum1, scales[3], product1, vl);
      accum2 = __riscv_vwmacc_vx_i32m1_m(
          upper_half, accum2, scales[5], product2, vl);
      accum3 = __riscv_vwmacc_vx_i32m1_m(
          upper_half, accum3, scales[7], product3, vl);
      low_bits += 32;
      activation += 128;
      scales += 8;
    }

    const vint32m1_t zero = __riscv_vmv_v_x_i32m1(0, 1);
    const vint32m1_t sum01 = __riscv_vredsum_vs_i32m1_i32m1(
        __riscv_vadd_vv_i32m1(accum0, accum1, 32), zero, 32);
    const vint32m1_t sum = __riscv_vredsum_vs_i32m1_i32m1(
        __riscv_vadd_vv_i32m1(accum2, accum3, 32), sum01, 32);
    result += fp16_to_fp32(x[block].d) * y[block].d *
              (float)__riscv_vmv_x_s_i32m1_i32(sum);
  }
  return result;
}

float q4km_vec_dot_q4_K_q8_K(const block_q4_K *x, const block_q8_K *y, int n) {
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
    const vint16mf2_t sums0 = __riscv_vlse16_v_i16mf2(y[block].bsums, 4, vl8);
    const vint16mf2_t sums1 = __riscv_vlse16_v_i16mf2(y[block].bsums + 1, 4, vl8);
    const vint16mf2_t sums = __riscv_vadd_vv_i16mf2(sums0, sums1, vl8);
    const vuint8mf4_t mins8 = __riscv_vle8_v_u8mf4(mins, vl8);
    const vint16mf2_t extended_mins = __riscv_vreinterpret_v_u16mf2_i16mf2(
        __riscv_vzext_vf2_u16mf2(mins8, vl8));
    const vint32m1_t min_products = __riscv_vwmul_vv_i32m1(sums, extended_mins, vl8);
    const vint32m1_t min_sum = __riscv_vredsum_vs_i32m1_i32m1(
        min_products, __riscv_vmv_v_x_i32m1(0, 1), vl8);
    result -= dmin * (float)__riscv_vmv_x_s_i32m1_i32(min_sum);

    const uint8_t *q4 = x[block].qs;
    const int8_t *q8 = y[block].qs;
    int32_t lower_sum = 0;
    int32_t upper_sum = 0;
    const size_t vl32 = 32;
    const vint16m1_t zero16 = __riscv_vmv_v_x_i16m1(0, 1);
    for (int group = 0; group < QK_K / 64; ++group) {
      const vuint8m1_t packed = __riscv_vle8_v_u8m1(q4, vl32);
      const vint8m1_t q8_lower = __riscv_vle8_v_i8m1(q8, vl32);
      const vint8m1_t q4_lower = __riscv_vreinterpret_v_u8m1_i8m1(
          __riscv_vand_vx_u8m1(packed, 0x0f, vl32));
      const vint16m2_t lower_products =
          __riscv_vwmul_vv_i16m2(q4_lower, q8_lower, vl32);
      const vint16m1_t reduced_lower = __riscv_vredsum_vs_i16m2_i16m1(
          lower_products, zero16, vl32);
      lower_sum += __riscv_vmv_x_s_i16m1_i16(reduced_lower) * scales[2 * group];

      const vint8m1_t q8_upper = __riscv_vle8_v_i8m1(q8 + 32, vl32);
      const vint8m1_t q4_upper = __riscv_vreinterpret_v_u8m1_i8m1(
          __riscv_vsrl_vx_u8m1(packed, 4, vl32));
      const vint16m2_t upper_products =
          __riscv_vwmul_vv_i16m2(q4_upper, q8_upper, vl32);
      const vint16m1_t reduced_upper = __riscv_vredsum_vs_i16m2_i16m1(
          upper_products, zero16, vl32);
      upper_sum += __riscv_vmv_x_s_i16m1_i16(reduced_upper) * scales[2 * group + 1];
      q4 += 32;
      q8 += 64;
    }
    result += d * (float)(lower_sum + upper_sum);
  }
  return result;
}

float q4km_vec_dot_q5_K_q8_K(const block_q5_K *x, const block_q8_K *y,
                             int n) {
  if (n <= 0 || n % QK_K != 0) return 0.0f;
  const uint32_t mask1 = 0x3f3f3f3fu;
  const uint32_t mask2 = 0x0f0f0f0fu;
  const uint32_t mask3 = 0x03030303u;
  float result = 0.0f;

  for (int block = 0; block < n / QK_K; ++block) {
    uint32_t unpacked[4];
    memcpy(unpacked, x[block].scales, 12);
    unpacked[3] = ((unpacked[2] >> 4) & mask2) |
                  (((unpacked[1] >> 6) & mask3) << 4);
    const uint32_t auxiliary = unpacked[1] & mask1;
    unpacked[1] = (unpacked[2] & mask2) |
                  (((unpacked[0] >> 6) & mask3) << 4);
    unpacked[2] = auxiliary;
    unpacked[0] &= mask1;
    const uint8_t *scales = (const uint8_t *)&unpacked[0];
    const uint8_t *mins = (const uint8_t *)&unpacked[2];
    const float d = fp16_to_fp32(x[block].d) * y[block].d;
    const float dmin = fp16_to_fp32(x[block].dmin) * y[block].d;

    const size_t vl8 = 8;
    const vint16m1_t sums0 =
        __riscv_vlse16_v_i16m1(y[block].bsums, 4, vl8);
    const vint16m1_t sums1 =
        __riscv_vlse16_v_i16m1(y[block].bsums + 1, 4, vl8);
    const vint16m1_t sums = __riscv_vadd_vv_i16m1(sums0, sums1, vl8);
    const vuint8mf2_t mins8 = __riscv_vle8_v_u8mf2(mins, vl8);
    const vint16m1_t extended_mins = __riscv_vreinterpret_v_u16m1_i16m1(
        __riscv_vzext_vf2_u16m1(mins8, vl8));
    const vint32m2_t min_products =
        __riscv_vwmul_vv_i32m2(sums, extended_mins, vl8);
    const vint32m1_t min_sum = __riscv_vredsum_vs_i32m2_i32m1(
        min_products, __riscv_vmv_v_x_i32m1(0, 1), vl8);
    result -= dmin * (float)__riscv_vmv_x_s_i32m1_i32(min_sum);

    const uint8_t *low_bits = x[block].qs;
    const uint8_t *high_bits = x[block].qh;
    const int8_t *activation = y[block].qs;
    const size_t vl = 32;
    const vuint8m2_t high = __riscv_vle8_v_u8m2(high_bits, vl);
    const vint32m1_t zero = __riscv_vmv_v_x_i32m1(0, 1);
    uint8_t high_mask = 1;
    int scale_index = 0;
    int32_t integer_sum = 0;

    for (int group = 0; group < QK_K / 64; ++group) {
      const vuint8m2_t packed = __riscv_vle8_v_u8m2(low_bits, vl);
      const vint8m2_t q8_low =
          __riscv_vle8_v_i8m2(activation, vl);
      const vint8m2_t q8_high =
          __riscv_vle8_v_i8m2(activation + 32, vl);

      const vint8m2_t low = __riscv_vreinterpret_v_u8m2_i8m2(
          __riscv_vand_vx_u8m2(packed, 0x0f, vl));
      const vbool4_t low_has_high = __riscv_vmsne_vx_u8m2_b4(
          __riscv_vand_vx_u8m2(high, high_mask, vl), 0, vl);
      const vint8m2_t quant_low =
          __riscv_vadd_vx_i8m2_mu(low_has_high, low, low, 16, vl);
      high_mask <<= 1;

      const vint8m2_t upper = __riscv_vreinterpret_v_u8m2_i8m2(
          __riscv_vsrl_vx_u8m2(packed, 4, vl));
      const vbool4_t upper_has_high = __riscv_vmsne_vx_u8m2_b4(
          __riscv_vand_vx_u8m2(high, high_mask, vl), 0, vl);
      const vint8m2_t quant_high =
          __riscv_vadd_vx_i8m2_mu(upper_has_high, upper, upper, 16, vl);
      high_mask <<= 1;

      const vint16m4_t product_low =
          __riscv_vwmul_vv_i16m4(quant_low, q8_low, vl);
      const vint16m4_t product_high =
          __riscv_vwmul_vv_i16m4(quant_high, q8_high, vl);
      const vint32m8_t scaled_low =
          __riscv_vwmul_vx_i32m8(product_low, scales[scale_index++], vl);
      const vint32m8_t scaled_high =
          __riscv_vwmul_vx_i32m8(product_high, scales[scale_index++], vl);
      const vint32m1_t reduced_low =
          __riscv_vredsum_vs_i32m8_i32m1(scaled_low, zero, vl);
      const vint32m1_t reduced =
          __riscv_vredsum_vs_i32m8_i32m1(scaled_high, reduced_low, vl);
      integer_sum += __riscv_vmv_x_s_i32m1_i32(reduced);
      low_bits += 32;
      activation += 64;
    }
    result += d * (float)integer_sum;
  }
  return result;
}

float q4km_vec_dot_q6_K_q8_K(const block_q6_K *x, const block_q8_K *y, int n) {
  const int blocks = n / QK_K;
  const vuint16mf2_t indices = __riscv_vid_v_u16mf2(32);
  const vbool32_t upper_mask = __riscv_vmsgtu_vx_u16mf2_b32(indices, 15, 32);
  float result = 0.0f;

  for (int block = 0; block < blocks; ++block) {
    const uint8_t *q6 = x[block].ql;
    const uint8_t *qh = x[block].qh;
    const int8_t *q8 = y[block].qs;
    const int8_t *scales = x[block].scales;
    const size_t vl = 32;
    vint32m1_t accum0 = __riscv_vmv_v_x_i32m1(0, vl);
    vint32m1_t accum1 = __riscv_vmv_v_x_i32m1(0, vl);
    vint32m1_t accum2 = __riscv_vmv_v_x_i32m1(0, vl);
    vint32m1_t accum3 = __riscv_vmv_v_x_i32m1(0, vl);
    int scale_index = 0;

    for (int group = 0; group < QK_K / 128; ++group) {
      const vuint8mf4_t high = __riscv_vle8_v_u8mf4(qh, vl);
      const vuint8mf4_t low0 = __riscv_vle8_v_u8mf4(q6, vl);
      const vuint8mf4_t low1 = __riscv_vle8_v_u8mf4(q6 + 32, vl);
      const vuint8mf4_t low_nibble0 = __riscv_vand_vx_u8mf4(low0, 0x0f, vl);
      const vuint8mf4_t low_nibble1 = __riscv_vand_vx_u8mf4(low1, 0x0f, vl);
      const vuint8mf4_t high_nibble0 = __riscv_vsrl_vx_u8mf4(low0, 4, vl);
      const vuint8mf4_t high_nibble1 = __riscv_vsrl_vx_u8mf4(low1, 4, vl);
      const vuint8mf4_t high0 = __riscv_vand_vx_u8mf4(high, 3, vl);
      const vuint8mf4_t high1 =
          __riscv_vand_vx_u8mf4(__riscv_vsrl_vx_u8mf4(high, 2, vl), 3, vl);
      const vuint8mf4_t high2 =
          __riscv_vand_vx_u8mf4(__riscv_vsrl_vx_u8mf4(high, 4, vl), 3, vl);
      const vuint8mf4_t high3 =
          __riscv_vand_vx_u8mf4(__riscv_vsrl_vx_u8mf4(high, 6, vl), 3, vl);

#define Q6_VALUE(low, high_bits)                                                   \
  __riscv_vreinterpret_v_u8mf4_i8mf4(                                             \
      __riscv_vor_vv_u8mf4((low), __riscv_vsll_vx_u8mf4((high_bits), 4, vl), vl))
      const vint8mf4_t value0 = __riscv_vsub_vx_i8mf4(Q6_VALUE(low_nibble0, high0), 32, vl);
      const vint8mf4_t value1 = __riscv_vsub_vx_i8mf4(Q6_VALUE(low_nibble1, high1), 32, vl);
      const vint8mf4_t value2 = __riscv_vsub_vx_i8mf4(Q6_VALUE(high_nibble0, high2), 32, vl);
      const vint8mf4_t value3 = __riscv_vsub_vx_i8mf4(Q6_VALUE(high_nibble1, high3), 32, vl);
#undef Q6_VALUE

      const vint16mf2_t product0 =
          __riscv_vwmul_vv_i16mf2(value0, __riscv_vle8_v_i8mf4(q8, vl), vl);
      const vint16mf2_t product1 =
          __riscv_vwmul_vv_i16mf2(value1, __riscv_vle8_v_i8mf4(q8 + 32, vl), vl);
      const vint16mf2_t product2 =
          __riscv_vwmul_vv_i16mf2(value2, __riscv_vle8_v_i8mf4(q8 + 64, vl), vl);
      const vint16mf2_t product3 =
          __riscv_vwmul_vv_i16mf2(value3, __riscv_vle8_v_i8mf4(q8 + 96, vl), vl);

      accum0 = __riscv_vwmacc_vx_i32m1(accum0, scales[scale_index], product0, 16);
      accum1 = __riscv_vwmacc_vx_i32m1(accum1, scales[scale_index + 2], product1, 16);
      accum2 = __riscv_vwmacc_vx_i32m1(accum2, scales[scale_index + 4], product2, 16);
      accum3 = __riscv_vwmacc_vx_i32m1(accum3, scales[scale_index + 6], product3, 16);
      accum0 = __riscv_vwmacc_vx_i32m1_m(
          upper_mask, accum0, scales[scale_index + 1], product0, vl);
      accum1 = __riscv_vwmacc_vx_i32m1_m(
          upper_mask, accum1, scales[scale_index + 3], product1, vl);
      accum2 = __riscv_vwmacc_vx_i32m1_m(
          upper_mask, accum2, scales[scale_index + 5], product2, vl);
      accum3 = __riscv_vwmacc_vx_i32m1_m(
          upper_mask, accum3, scales[scale_index + 7], product3, vl);
      q6 += 64;
      qh += 32;
      q8 += 128;
      scale_index = 8;
    }

    const vint32m1_t zero = __riscv_vmv_v_x_i32m1(0, 1);
    const vint32m1_t sum0 = __riscv_vredsum_vs_i32m1_i32m1(
        __riscv_vadd_vv_i32m1(accum0, accum1, vl), zero, vl);
    const vint32m1_t sum1 = __riscv_vredsum_vs_i32m1_i32m1(
        __riscv_vadd_vv_i32m1(accum2, accum3, vl), sum0, vl);
    const int32_t integer_sum = __riscv_vmv_x_s_i32m1_i32(sum1);
    result += fp16_to_fp32(x[block].d) * y[block].d * (float)integer_sum;
  }
  return result;
}

float q4km_vec_dot_q8_0_q8_0(const block_q8_0 *x, const block_q8_0 *y,
                             int n) {
  if (n <= 0 || n % QK8_0 != 0) return 0.0f;
  const size_t vl = QK8_0;
  float result = 0.0f;

  for (int block = 0; block < n / QK8_0; ++block) {
    const vint8m2_t weight = __riscv_vle8_v_i8m2(x[block].qs, vl);
    const vint8m2_t activation = __riscv_vle8_v_i8m2(y[block].qs, vl);
    const vint16m4_t products =
        __riscv_vwmul_vv_i16m4(weight, activation, vl);
    const vint32m1_t sum = __riscv_vwredsum_vs_i16m4_i32m1(
        products, __riscv_vmv_v_x_i32m1(0, 1), vl);
    result += (float)__riscv_vmv_x_s_i32m1_i32(sum) *
              fp16_to_fp32(x[block].d) * fp16_to_fp32(y[block].d);
  }
  return result;
}
