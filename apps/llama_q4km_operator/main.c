#include "../llama_q4km_micro/micro_kernels.h"

#include <math.h>
#include <riscv_vector.h>
#include <stddef.h>
#include <stdint.h>

#include "../../software/akv/include/akv/akv.h"
#include "runtime.h"

#ifdef SPIKE
#define REPORT(...) do { } while (0)
#ifdef SPIKE_DIAGNOSTICS
extern void printhex(uint64_t value);
extern void printstr(const char *text);
#endif
#else
#include "printf.h"
#define REPORT(...) printf(__VA_ARGS__)
#endif

enum {
  CASE_LINEAR_Q4 = 1,
  CASE_LINEAR_Q6 = 2,
  CASE_ADD = 3,
  CASE_SILU_MUL = 4,
  CASE_RMS_NORM = 5,
  CASE_ROPE = 6,
  CASE_ATTENTION = 7,
  CASE_SET_ROWS_F32_F16 = 8,
  CASE_GET_ROWS_F32 = 9,
  CASE_GET_ROWS_Q4_K = 10,
};

enum {
  CASE_FLAG_ATTENTION_RVV = 1u << 0,
  CASE_FLAG_ATTENTION_AKV = 1u << 1,
  CASE_FLAG_ATTENTION_TILED_RVV = 1u << 2,
  CASE_FLAG_ATTENTION_AKV_V2 = 1u << 3,
  ATTENTION_PHASE_Q_CONVERT = 1,
  ATTENTION_PHASE_ONLINE_KV = 2,
  ATTENTION_PHASE_OUTPUT = 3,
  MAX_ATTENTION_DIM = 256,
  MAX_ATTENTION_TOKENS = 15,
  MAX_ATTENTION_HEADS = 12,
  MAX_ATTENTION_KV = 1024,
  MAX_OPERATOR_ELEMENTS = 8960 * 17,
  MAX_CACHE_WIDTH = 256,
  MAX_CACHE_ROWS = 256,
  TILED_RVV_Q_ROWS = 6,
  TILED_RVV_DIM = 128,
  TILED_RVV_KV_TILE = 64,
};

typedef struct {
  uint32_t magic;
  uint32_t version;
  uint32_t kind;
  uint32_t flags;
  uint32_t args[8];
  float params[8];
  struct {
    uint32_t shape[4];
    uint32_t bytes;
  } tensors[5];
} case_config_t;

extern const case_config_t llama_case_config;
extern const char llama_case_name[];
extern const uint8_t llama_input_a_start[];
extern const uint8_t llama_input_b_start[];
extern const uint8_t llama_input_c_start[];
extern const uint8_t llama_input_d_start[];
extern const uint8_t llama_golden_start[];

static block_q8_K quantized[8960 / QK_K];
static float scratch[256];
static float operator_output[MAX_OPERATOR_ELEMENTS]
    __attribute__((aligned(64)));
static _Float16 operator_output_f16[MAX_CACHE_WIDTH * MAX_CACHE_ROWS]
    __attribute__((aligned(64)));
static float attention_output[MAX_ATTENTION_DIM * MAX_ATTENTION_TOKENS *
                              MAX_ATTENTION_HEADS];
static _Float16 attention_query_f16[MAX_ATTENTION_DIM];
static _Float16 attention_accum_f16[MAX_ATTENTION_DIM];
static _Float16 attention_query_group_f16[AKV_MAX_Q_ROWS *
                                          MAX_ATTENTION_DIM]
    __attribute__((aligned(64)));
static _Float16 attention_tiled_query[TILED_RVV_Q_ROWS][MAX_ATTENTION_DIM]
    __attribute__((aligned(64)));
static _Float16 attention_tiled_accum[TILED_RVV_Q_ROWS][MAX_ATTENTION_DIM]
    __attribute__((aligned(64)));
static _Float16 attention_tiled_key[MAX_ATTENTION_DIM][TILED_RVV_KV_TILE]
    __attribute__((aligned(64)));
static _Float16 attention_tiled_value[TILED_RVV_KV_TILE][MAX_ATTENTION_DIM]
    __attribute__((aligned(64)));
static float attention_tiled_score[TILED_RVV_Q_ROWS][TILED_RVV_KV_TILE]
    __attribute__((aligned(64)));
static float attention_tiled_maximum[TILED_RVV_Q_ROWS];
static float attention_tiled_sum[TILED_RVV_Q_ROWS];
static float attention_tiled_old_scale[TILED_RVV_Q_ROWS];
static akv_device_t attention_akv_device;
static akv_attention_plan_t attention_akv_plan;
static akv_attention_v2_workspace_t attention_akv_v2_workspace;

static inline uint64_t read_cycle(void) {
#ifdef SPIKE
  return 0;
#else
  uint64_t value;
  asm volatile("fence rw, rw; csrr %0, cycle" : "=r"(value) : : "memory");
  return value;
#endif
}

static float absf(float value) { return value < 0.0f ? -value : value; }

static int close_f32(float actual, float expected, float atol, float rtol) {
  return absf(actual - expected) <= atol + rtol * absf(expected);
}

static float fp16_to_fp32(uint16_t bits) {
  _Float16 value;
  __builtin_memcpy(&value, &bits, sizeof(bits));
  return (float)value;
}

static float negative_infinity_f32(void) {
  const uint32_t bits = 0xff800000u;
  float value;
  __builtin_memcpy(&value, &bits, sizeof(value));
  return value;
}

static __attribute__((always_inline)) inline vfloat32m2_t vector_expf(
    vfloat32m2_t x, size_t vl) {
  const vfloat32m2_t r = __riscv_vfmv_v_f_f32m2(0x1.8p23f, vl);
  const vfloat32m2_t z = __riscv_vfmacc_vf_f32m2(r, 0x1.715476p+0f, x, vl);
  const vfloat32m2_t n = __riscv_vfsub_vv_f32m2(z, r, vl);
  const vfloat32m2_t b = __riscv_vfnmsac_vf_f32m2(
      __riscv_vfnmsac_vf_f32m2(x, 0x1.62e4p-1f, n, vl),
      0x1.7f7d1cp-20f, n, vl);
  const vuint32m2_t e = __riscv_vsll_vx_u32m2(
      __riscv_vreinterpret_v_f32m2_u32m2(z), 23, vl);
  const vfloat32m2_t k = __riscv_vreinterpret_v_u32m2_f32m2(
      __riscv_vadd_vx_u32m2(e, 0x3f800000, vl));
  const vfloat32m2_t u = __riscv_vfmul_vv_f32m2(b, b, vl);
  const vfloat32m2_t j = __riscv_vfmacc_vv_f32m2(
      __riscv_vfmul_vf_f32m2(b, 0x1.ffffecp-1f, vl),
      __riscv_vfmacc_vv_f32m2(
          __riscv_vfmacc_vf_f32m2(
              __riscv_vfmv_v_f_f32m2(0x1.fffdb6p-2f, vl),
              0x1.555e66p-3f, b, vl),
          __riscv_vfmacc_vf_f32m2(
              __riscv_vfmv_v_f_f32m2(0x1.573e2ep-5f, vl),
              0x1.0e4020p-7f, b, vl),
          u, vl),
      u, vl);
  return __riscv_vfmacc_vv_f32m2(k, j, k, vl);
}

static void run_linear(const case_config_t *cfg) {
  const int k = cfg->args[0];
  const int output_rows = cfg->args[1];
  const int columns = cfg->args[2];
  const float *activation = (const float *)llama_input_b_start;
  const int blocks = k / QK_K;

  for (int column = 0; column < columns; ++column) {
    q4km_quantize_row_q8_K(activation + (size_t)column * k, quantized, k);
    for (int row = 0; row < output_rows; ++row) {
      float *actual = &operator_output[(size_t)column * output_rows + row];
      if (cfg->kind == CASE_LINEAR_Q4) {
        *actual = q4km_vec_dot_q4_K_q8_K(
            (const block_q4_K *)llama_input_a_start + (size_t)row * blocks,
            quantized, k);
      } else {
        *actual = q4km_vec_dot_q6_K_q8_K(
            (const block_q6_K *)llama_input_a_start + (size_t)row * blocks,
            quantized, k);
      }
    }
  }
}

static void run_add(const case_config_t *cfg) {
  const float *a = (const float *)llama_input_a_start;
  const float *b = (const float *)llama_input_b_start;
  const size_t count = cfg->args[0];
  for (size_t offset = 0; offset < count;) {
    const size_t vl = __riscv_vsetvl_e32m8(count - offset);
    const vfloat32m8_t result = __riscv_vfadd_vv_f32m8(
        __riscv_vle32_v_f32m8(a + offset, vl),
        __riscv_vle32_v_f32m8(b + offset, vl), vl);
    __riscv_vse32_v_f32m8(operator_output + offset, result, vl);
    offset += vl;
  }
}

static void run_silu_mul(const case_config_t *cfg) {
  const float *a = (const float *)llama_input_a_start;
  const float *b = (const float *)llama_input_b_start;
  const size_t count = cfg->args[0];
  for (size_t offset = 0; offset < count;) {
    const size_t vl = __riscv_vsetvl_e32m2(count - offset);
    const vfloat32m2_t x = __riscv_vle32_v_f32m2(a + offset, vl);
    const vfloat32m2_t denominator = __riscv_vfadd_vf_f32m2(
        vector_expf(__riscv_vfneg_v_f32m2(x, vl), vl), 1.0f, vl);
    const vfloat32m2_t silu = __riscv_vfdiv_vv_f32m2(x, denominator, vl);
    const vfloat32m2_t result = __riscv_vfmul_vv_f32m2(
        silu, __riscv_vle32_v_f32m2(b + offset, vl), vl);
    __riscv_vse32_v_f32m2(operator_output + offset, result, vl);
    offset += vl;
  }
}

static void run_rms_norm(const case_config_t *cfg) {
  const float *input = (const float *)llama_input_a_start;
  const float *weight = (const float *)llama_input_b_start;
  const int width = cfg->args[0];
  const int rows = cfg->args[1];

  for (int row = 0; row < rows; ++row) {
    const float *x = input + (size_t)row * width;
    double sum = 0.0;
    for (int item = 0; item < width; ++item) {
      sum += (double)(x[item] * x[item]);
    }
    const float scale = 1.0f / sqrtf((float)(sum / width) + cfg->params[2]);
    for (int offset = 0; offset < width;) {
      const size_t vl = __riscv_vsetvl_e32m8(width - offset);
      vfloat32m8_t result = __riscv_vfmul_vf_f32m8(
          __riscv_vle32_v_f32m8(x + offset, vl), scale, vl);
      result = __riscv_vfmul_vv_f32m8(
          result, __riscv_vle32_v_f32m8(weight + offset, vl), vl);
      __riscv_vse32_v_f32m8(
          operator_output + (size_t)row * width + offset, result, vl);
      offset += vl;
    }
  }
}

static void run_rope(const case_config_t *cfg) {
  const float *input = (const float *)llama_input_a_start;
  const int32_t *position = (const int32_t *)llama_input_b_start;
  const int n_dims = cfg->args[0];
  const int mode = cfg->args[1];
  const int width = cfg->args[2];
  const int heads = cfg->args[3];
  const int tokens = cfg->args[4];
  const float theta_scale = powf(cfg->params[2], -2.0f / n_dims);

  if (mode != 2 || width != n_dims) return;
  for (int token = 0; token < tokens; ++token) {
    float theta = (float)position[token];
    for (int pair = 0; pair < n_dims / 2; ++pair) {
      scratch[2 * pair] = cosf(theta) * cfg->params[5];
      scratch[2 * pair + 1] = sinf(theta) * cfg->params[5];
      theta *= theta_scale;
    }
    for (int head = 0; head < heads; ++head) {
      const size_t base = ((size_t)token * heads + head) * width;
      for (int pair = 0; pair < n_dims / 2; ++pair) {
        const float x0 = input[base + pair];
        const float x1 = input[base + pair + n_dims / 2];
        const float c = scratch[2 * pair];
        const float s = scratch[2 * pair + 1];
        operator_output[base + pair] = x0 * c - x1 * s;
        operator_output[base + pair + n_dims / 2] = x0 * s + x1 * c;
      }
    }
  }
}

static void run_set_rows_f32_f16(const case_config_t *cfg) {
  const float *input = (const float *)llama_input_a_start;
  const int64_t *indices = (const int64_t *)llama_input_b_start;
  const size_t width = cfg->args[0];
  const size_t rows = cfg->args[1];

  for (size_t row = 0; row < rows; ++row) {
    _Float16 *destination = operator_output_f16 + (size_t)indices[row] * width;
    for (size_t offset = 0; offset < width;) {
      const size_t vl = __riscv_vsetvl_e32m8(width - offset);
      const vfloat32m8_t values =
          __riscv_vle32_v_f32m8(input + row * width + offset, vl);
      __riscv_vse16_v_f16m4(
          destination + offset, __riscv_vfncvt_f_f_w_f16m4(values, vl), vl);
      offset += vl;
    }
  }
}

static void run_get_rows_f32(const case_config_t *cfg) {
  const float *source = (const float *)llama_input_a_start;
  const int32_t *indices = (const int32_t *)llama_input_b_start;
  const size_t width = cfg->args[0];
  const size_t rows = cfg->args[1];

  for (size_t row = 0; row < rows; ++row) {
    const float *selected = source + (size_t)indices[row] * width;
    for (size_t offset = 0; offset < width;) {
      const size_t vl = __riscv_vsetvl_e32m8(width - offset);
      __riscv_vse32_v_f32m8(
          operator_output + row * width + offset,
          __riscv_vle32_v_f32m8(selected + offset, vl), vl);
      offset += vl;
    }
  }
}

static void get_scale_min_k4(int index, const uint8_t *packed,
                             uint8_t *scale, uint8_t *minimum) {
  if (index < 4) {
    *scale = packed[index] & 63;
    *minimum = packed[index + 4] & 63;
  } else {
    *scale = (packed[index + 4] & 0x0f) |
             ((packed[index - 4] >> 6) << 4);
    *minimum = (packed[index + 4] >> 4) |
               ((packed[index] >> 6) << 4);
  }
}

static void dequantize_q4_k_row(const block_q4_K *source, float *destination,
                                size_t width) {
  for (size_t block = 0; block < width / QK_K; ++block) {
    const uint8_t *quant = source[block].qs;
    const float d = fp16_to_fp32(source[block].d);
    const float dmin = fp16_to_fp32(source[block].dmin);
    int scale_index = 0;
    for (int group = 0; group < QK_K / 64; ++group) {
      uint8_t scale0;
      uint8_t scale1;
      uint8_t min0;
      uint8_t min1;
      get_scale_min_k4(scale_index, source[block].scales, &scale0, &min0);
      get_scale_min_k4(scale_index + 1, source[block].scales, &scale1, &min1);
      const float d0 = d * scale0;
      const float d1 = d * scale1;
      const float m0 = dmin * min0;
      const float m1 = dmin * min1;
      for (int item = 0; item < 32; ++item)
        *destination++ = d0 * (quant[item] & 0x0f) - m0;
      for (int item = 0; item < 32; ++item)
        *destination++ = d1 * (quant[item] >> 4) - m1;
      quant += 32;
      scale_index += 2;
    }
  }
}

static void run_get_rows_q4_k(const case_config_t *cfg) {
  const block_q4_K *source = (const block_q4_K *)llama_input_a_start;
  const int32_t *indices = (const int32_t *)llama_input_b_start;
  const size_t width = cfg->args[0];
  const size_t rows = cfg->args[1];
  const size_t blocks_per_row = width / QK_K;

  for (size_t row = 0; row < rows; ++row) {
    dequantize_q4_k_row(source + (size_t)indices[row] * blocks_per_row,
                        operator_output + row * width, width);
  }
}

static size_t operator_element_count(const case_config_t *cfg) {
  switch (cfg->kind) {
    case CASE_LINEAR_Q4:
    case CASE_LINEAR_Q6: return (size_t)cfg->args[1] * cfg->args[2];
    case CASE_ADD:
    case CASE_SILU_MUL: return cfg->args[0];
    case CASE_RMS_NORM: return (size_t)cfg->args[0] * cfg->args[1];
    case CASE_ROPE:
      return (size_t)cfg->args[2] * cfg->args[3] * cfg->args[4];
    case CASE_GET_ROWS_F32:
    case CASE_GET_ROWS_Q4_K: return (size_t)cfg->args[0] * cfg->args[1];
    default: return 0;
  }
}

static int check_operator(const case_config_t *cfg) {
  const float *golden = (const float *)llama_golden_start;
  const size_t count = operator_element_count(cfg);
  int failures = 0;
  for (size_t item = 0; item < count; ++item) {
    failures += !close_f32(operator_output[item], golden[item],
                           cfg->params[0], cfg->params[1]);
  }
  return failures;
}

static int check_set_rows(const case_config_t *cfg) {
  const uint16_t *golden = (const uint16_t *)llama_golden_start;
  const int64_t *indices = (const int64_t *)llama_input_b_start;
  const size_t width = cfg->args[0];
  const size_t rows = cfg->args[1];
  int failures = 0;
  for (size_t row = 0; row < rows; ++row) {
    const uint16_t *actual = (const uint16_t *)(operator_output_f16 +
                                                (size_t)indices[row] * width);
    for (size_t item = 0; item < width; ++item)
      failures += actual[item] != golden[row * width + item];
  }
  return failures;
}

static int operator_config_is_valid(const case_config_t *cfg) {
  if (cfg->kind == CASE_ROPE) {
    if (cfg->args[0] == 0 || cfg->args[1] != 2 ||
        cfg->args[2] != cfg->args[0] ||
        operator_element_count(cfg) > MAX_OPERATOR_ELEMENTS)
      return 0;
  } else if (cfg->kind == CASE_SET_ROWS_F32_F16) {
    const int64_t *indices = (const int64_t *)llama_input_b_start;
    if (cfg->args[0] == 0 || cfg->args[0] > MAX_CACHE_WIDTH ||
        cfg->args[1] == 0 || cfg->args[2] == 0 ||
        cfg->args[2] > MAX_CACHE_ROWS)
      return 0;
    for (size_t row = 0; row < cfg->args[1]; ++row)
      if (indices[row] < 0 || indices[row] >= cfg->args[2]) return 0;
  } else if (cfg->kind == CASE_GET_ROWS_F32 ||
             cfg->kind == CASE_GET_ROWS_Q4_K) {
    const int32_t *indices = (const int32_t *)llama_input_b_start;
    if (cfg->args[0] == 0 || cfg->args[1] == 0 ||
        operator_element_count(cfg) > MAX_OPERATOR_ELEMENTS)
      return 0;
    for (size_t row = 0; row < cfg->args[1]; ++row)
      if (indices[row] < 0 ||
          (uint32_t)indices[row] >= cfg->tensors[0].shape[1])
        return 0;
  }
  return 1;
}

static int attention_shape_is_supported(const case_config_t *cfg) {
  return cfg->args[0] > 0 && cfg->args[0] <= MAX_ATTENTION_DIM &&
         cfg->args[1] > 0 && cfg->args[1] <= MAX_ATTENTION_TOKENS &&
         cfg->args[2] > 0 && cfg->args[2] <= MAX_ATTENTION_HEADS &&
         cfg->args[3] > 0 && cfg->args[3] <= MAX_ATTENTION_KV &&
         cfg->args[4] > 0 && cfg->args[2] % cfg->args[4] == 0;
}

static void run_attention_reference(const case_config_t *cfg) {
  const float *query = (const float *)llama_input_a_start;
  const _Float16 *key = (const _Float16 *)llama_input_b_start;
  const _Float16 *value = (const _Float16 *)llama_input_c_start;
  const uint16_t *mask = (const uint16_t *)llama_input_d_start;
  const int dim = cfg->args[0];
  const int tokens = cfg->args[1];
  const int qheads = cfg->args[2];
  const int kvlen = cfg->args[3];
  const int kvheads = cfg->args[4];
  const int heads_per_kv = qheads / kvheads;

  for (int qhead = 0; qhead < qheads; ++qhead) {
    const int kvhead = qhead / heads_per_kv;
    for (int token = 0; token < tokens; ++token) {
      const float *q = query + ((size_t)qhead * tokens + token) * dim;
      HW_CNT_PHASE(ATTENTION_PHASE_Q_CONVERT);
      for (int item = 0; item < dim; ++item) {
        attention_query_f16[item] = (_Float16)q[item];
        attention_accum_f16[item] = (_Float16)0.0f;
      }

      float sum_weights = 0.0f;
      float maximum = negative_infinity_f32();
      HW_CNT_PHASE(ATTENTION_PHASE_ONLINE_KV);
      for (int sequence = 0; sequence < kvlen; ++sequence) {
        const uint16_t mask_bits = mask[(size_t)token * kvlen + sequence];
        if (mask_bits == 0xfc00u) continue;

        const _Float16 *k = key + ((size_t)kvhead * kvlen + sequence) * dim;
        double dot = 0.0;
        for (int item = 0; item < dim; ++item) {
          dot += (float)k[item] * (float)attention_query_f16[item];
        }
        const float score = (float)dot * cfg->params[2] + fp16_to_fp32(mask_bits);
        const float old_maximum = maximum;
        float old_scale = 1.0f;
        float weight = 1.0f;
        if (score > maximum) {
          maximum = score;
          old_scale = expf(old_maximum - maximum);
          for (int item = 0; item < dim; ++item) {
            attention_accum_f16[item] =
                (_Float16)((float)attention_accum_f16[item] * old_scale);
          }
        } else {
          weight = expf(score - maximum);
        }

        const _Float16 *v = value + ((size_t)kvhead * kvlen + sequence) * dim;
        for (int item = 0; item < dim; ++item) {
          attention_accum_f16[item] = (_Float16)(
              (float)attention_accum_f16[item] + (float)v[item] * weight);
        }
        sum_weights = sum_weights * old_scale + weight;
      }

      HW_CNT_PHASE(ATTENTION_PHASE_OUTPUT);
      const float inverse = sum_weights == 0.0f ? 0.0f : 1.0f / sum_weights;
      for (int item = 0; item < dim; ++item) {
        const size_t output_index = ((size_t)token * qheads + qhead) * dim + item;
        attention_output[output_index] = (float)attention_accum_f16[item] * inverse;
      }
    }
  }
}

static float dot_f16_rvv(const _Float16 *lhs, const _Float16 *rhs, int count) {
  size_t vl = __riscv_vsetvlmax_e32m2();
  vfloat32m2_t products = __riscv_vfmv_v_f_f32m2(0.0f, vl);
  for (int offset = 0; offset < count;) {
    vl = __riscv_vsetvl_e16m1(count - offset);
    const vfloat16m1_t x = __riscv_vle16_v_f16m1(lhs + offset, vl);
    const vfloat16m1_t y = __riscv_vle16_v_f16m1(rhs + offset, vl);
    products = __riscv_vfwmacc_vv_f32m2_tu(products, x, y, vl);
    offset += (int)vl;
  }

  vl = __riscv_vsetvlmax_e32m1();
  const vfloat32m1_t folded = __riscv_vfadd_vv_f32m1(
      __riscv_vget_v_f32m2_f32m1(products, 0),
      __riscv_vget_v_f32m2_f32m1(products, 1), vl);
  const vfloat32m1_t zero = __riscv_vfmv_v_f_f32m1(0.0f, 1);
  const vfloat32m1_t reduced =
      __riscv_vfredusum_vs_f32m1_f32m1(folded, zero, vl);
  return __riscv_vfmv_f_s_f32m1_f32(reduced);
}

static void convert_f32_to_f16_rvv(_Float16 *destination, const float *source,
                                   int count) {
  for (int offset = 0; offset < count;) {
    const size_t vl = __riscv_vsetvl_e32m4(count - offset);
    const vfloat32m4_t values = __riscv_vle32_v_f32m4(source + offset, vl);
    __riscv_vse16_v_f16m2(
        destination + offset,
        __riscv_vfncvt_f_f_w_f16m2(values, vl), vl);
    offset += (int)vl;
  }
}

static void clear_attention_accum_rvv(int count) {
  for (int offset = 0; offset < count;) {
    const size_t vl = __riscv_vsetvl_e16m4(count - offset);
    __riscv_vse16_v_f16m4(
        attention_accum_f16 + offset,
        __riscv_vfmv_v_f_f16m4((_Float16)0.0f, vl), vl);
    offset += (int)vl;
  }
}

static void scale_attention_accum_rvv(float factor, int count) {
  const _Float16 factor_f16 = (_Float16)factor;
  for (int offset = 0; offset < count;) {
    const size_t vl = __riscv_vsetvl_e16m4(count - offset);
    const vfloat16m4_t accum =
        __riscv_vle16_v_f16m4(attention_accum_f16 + offset, vl);
    __riscv_vse16_v_f16m4(
        attention_accum_f16 + offset,
        __riscv_vfmul_vf_f16m4(accum, factor_f16, vl), vl);
    offset += (int)vl;
  }
}

static void mad_attention_accum_rvv(const _Float16 *value, float factor,
                                    int count) {
  const _Float16 factor_f16 = (_Float16)factor;
  for (int offset = 0; offset < count;) {
    const size_t vl = __riscv_vsetvl_e16m4(count - offset);
    vfloat16m4_t accum =
        __riscv_vle16_v_f16m4(attention_accum_f16 + offset, vl);
    accum = __riscv_vfmacc_vf_f16m4(
        accum, factor_f16, __riscv_vle16_v_f16m4(value + offset, vl), vl);
    __riscv_vse16_v_f16m4(attention_accum_f16 + offset, accum, vl);
    offset += (int)vl;
  }
}

// D256 is sensitive to rounding the online-softmax weight to F16 before the
// value multiply. Keep the architectural F16 accumulator, but perform each
// scale/MAC with the original F32 weight and narrow only the updated state.
static void scale_attention_accum_rvv_f32_weight(float factor, int count) {
  for (int offset = 0; offset < count;) {
    const size_t vl = __riscv_vsetvl_e16m2(count - offset);
    const vfloat32m4_t scaled = __riscv_vfmul_vf_f32m4(
        __riscv_vfwcvt_f_f_v_f32m4(
            __riscv_vle16_v_f16m2(attention_accum_f16 + offset, vl), vl),
        factor, vl);
    __riscv_vse16_v_f16m2(
        attention_accum_f16 + offset,
        __riscv_vfncvt_f_f_w_f16m2(scaled, vl), vl);
    offset += (int)vl;
  }
}

static void mad_attention_accum_rvv_f32_weight(const _Float16 *value,
                                                float factor, int count) {
  for (int offset = 0; offset < count;) {
    const size_t vl = __riscv_vsetvl_e16m2(count - offset);
    const vfloat32m4_t accumulator = __riscv_vfwcvt_f_f_v_f32m4(
        __riscv_vle16_v_f16m2(attention_accum_f16 + offset, vl), vl);
    const vfloat32m4_t value_f32 = __riscv_vfwcvt_f_f_v_f32m4(
        __riscv_vle16_v_f16m2(value + offset, vl), vl);
    const vfloat32m4_t updated = __riscv_vfmacc_vf_f32m4(
        accumulator, factor, value_f32, vl);
    __riscv_vse16_v_f16m2(
        attention_accum_f16 + offset,
        __riscv_vfncvt_f_f_w_f16m2(updated, vl), vl);
    offset += (int)vl;
  }
}

static void store_attention_output_rvv(float *output, float factor, int count) {
  for (int offset = 0; offset < count;) {
    const size_t vl = __riscv_vsetvl_e16m4(count - offset);
    const vfloat16m4_t accum =
        __riscv_vle16_v_f16m4(attention_accum_f16 + offset, vl);
    const vfloat32m8_t widened = __riscv_vfwcvt_f_f_v_f32m8(accum, vl);
    __riscv_vse32_v_f32m8(
        output + offset, __riscv_vfmul_vf_f32m8(widened, factor, vl), vl);
    offset += (int)vl;
  }
}

static int attention_active_prefix(const uint16_t *mask, int kvlen) {
  int active = 0;
  while (active < kvlen && mask[active] != 0xfc00u) ++active;
  for (int sequence = active; sequence < kvlen; ++sequence) {
    if (mask[sequence] != 0xfc00u) return -1;
  }
  return active;
}

static float reduce_max_f32m2(vfloat32m2_t values, size_t vl) {
  const vfloat32m1_t initial =
      __riscv_vfmv_v_f_f32m1(negative_infinity_f32(), 1);
  const vfloat32m1_t reduced =
      __riscv_vfredmax_vs_f32m2_f32m1(values, initial, vl);
  return __riscv_vfmv_f_s_f32m1_f32(reduced);
}

static float reduce_sum_f32m2(vfloat32m2_t values, size_t vl) {
  const vfloat32m1_t initial = __riscv_vfmv_v_f_f32m1(0.0f, 1);
  const vfloat32m1_t reduced =
      __riscv_vfredusum_vs_f32m2_f32m1(values, initial, vl);
  return __riscv_vfmv_f_s_f32m1_f32(reduced);
}

static void prepare_tiled_query_rvv(const float *query, int dim) {
  for (int head = 0; head < TILED_RVV_Q_ROWS; ++head) {
    convert_f32_to_f16_rvv(attention_tiled_query[head],
                           query + (size_t)head * dim, dim);
    for (int offset = 0; offset < dim;) {
      const size_t vl = __riscv_vsetvl_e16m2(dim - offset);
      __riscv_vse16_v_f16m2(
          attention_tiled_accum[head] + offset,
          __riscv_vfmv_v_f_f16m2((_Float16)0.0f, vl), vl);
      offset += (int)vl;
    }
    attention_tiled_maximum[head] = negative_infinity_f32();
    attention_tiled_sum[head] = 0.0f;
  }
}

static void prepare_tiled_query4_d256_rvv(const float *query) {
  for (int head = 0; head < 4; ++head) {
    convert_f32_to_f16_rvv(attention_tiled_query[head],
                           query + (size_t)head * AKV_HEAD_DIM_256,
                           AKV_HEAD_DIM_256);
    for (int offset = 0; offset < AKV_HEAD_DIM_256;) {
      const size_t vl =
          __riscv_vsetvl_e16m2(AKV_HEAD_DIM_256 - offset);
      __riscv_vse16_v_f16m2(
          attention_tiled_accum[head] + offset,
          __riscv_vfmv_v_f_f16m2((_Float16)0.0f, vl), vl);
      offset += (int)vl;
    }
    attention_tiled_maximum[head] = negative_infinity_f32();
    attention_tiled_sum[head] = 0.0f;
  }
}

static void pack_tiled_kv_rvv(const _Float16 *key, const _Float16 *value,
                              int dim, int tile_tokens) {
  const ptrdiff_t key_stride =
      (ptrdiff_t)TILED_RVV_KV_TILE * (ptrdiff_t)sizeof(_Float16);
  for (int token = 0; token < tile_tokens; ++token) {
    for (int offset = 0; offset < dim;) {
      const size_t vl = __riscv_vsetvl_e16m2(dim - offset);
      const vfloat16m2_t key_values =
          __riscv_vle16_v_f16m2(key + (size_t)token * dim + offset, vl);
      const vfloat16m2_t value_values =
          __riscv_vle16_v_f16m2(value + (size_t)token * dim + offset, vl);
      __riscv_vsse16_v_f16m2(
          &attention_tiled_key[offset][token], key_stride, key_values, vl);
      __riscv_vse16_v_f16m2(
          &attention_tiled_value[token][offset], value_values, vl);
      offset += (int)vl;
    }
  }
}

static void compute_tiled_scores4_rvv(float scale, const _Float16 *mask,
                                      int dim, int tile_tokens) {
  const size_t vl = __riscv_vsetvl_e16m1(tile_tokens);
  vfloat32m2_t score0 = __riscv_vfmv_v_f_f32m2(0.0f, vl);
  vfloat32m2_t score1 = __riscv_vfmv_v_f_f32m2(0.0f, vl);
  vfloat32m2_t score2 = __riscv_vfmv_v_f_f32m2(0.0f, vl);
  vfloat32m2_t score3 = __riscv_vfmv_v_f_f32m2(0.0f, vl);

  for (int item = 0; item < dim; ++item) {
    const vfloat16m1_t key =
        __riscv_vle16_v_f16m1(attention_tiled_key[item], vl);
    score0 = __riscv_vfwmacc_vf_f32m2(
        score0, attention_tiled_query[0][item], key, vl);
    score1 = __riscv_vfwmacc_vf_f32m2(
        score1, attention_tiled_query[1][item], key, vl);
    score2 = __riscv_vfwmacc_vf_f32m2(
        score2, attention_tiled_query[2][item], key, vl);
    score3 = __riscv_vfwmacc_vf_f32m2(
        score3, attention_tiled_query[3][item], key, vl);
  }

  const vfloat32m2_t mask_f32 = __riscv_vfwcvt_f_f_v_f32m2(
      __riscv_vle16_v_f16m1(mask, vl), vl);
  score0 = __riscv_vfadd_vv_f32m2(
      __riscv_vfmul_vf_f32m2(score0, scale, vl), mask_f32, vl);
  score1 = __riscv_vfadd_vv_f32m2(
      __riscv_vfmul_vf_f32m2(score1, scale, vl), mask_f32, vl);
  score2 = __riscv_vfadd_vv_f32m2(
      __riscv_vfmul_vf_f32m2(score2, scale, vl), mask_f32, vl);
  score3 = __riscv_vfadd_vv_f32m2(
      __riscv_vfmul_vf_f32m2(score3, scale, vl), mask_f32, vl);
  __riscv_vse32_v_f32m2(attention_tiled_score[0], score0, vl);
  __riscv_vse32_v_f32m2(attention_tiled_score[1], score1, vl);
  __riscv_vse32_v_f32m2(attention_tiled_score[2], score2, vl);
  __riscv_vse32_v_f32m2(attention_tiled_score[3], score3, vl);
}

static void compute_tiled_scores2_rvv(float scale, const _Float16 *mask,
                                      int dim, int tile_tokens) {
  const size_t vl = __riscv_vsetvl_e16m1(tile_tokens);
  vfloat32m2_t score4 = __riscv_vfmv_v_f_f32m2(0.0f, vl);
  vfloat32m2_t score5 = __riscv_vfmv_v_f_f32m2(0.0f, vl);

  for (int item = 0; item < dim; ++item) {
    const vfloat16m1_t key =
        __riscv_vle16_v_f16m1(attention_tiled_key[item], vl);
    score4 = __riscv_vfwmacc_vf_f32m2(
        score4, attention_tiled_query[4][item], key, vl);
    score5 = __riscv_vfwmacc_vf_f32m2(
        score5, attention_tiled_query[5][item], key, vl);
  }

  const vfloat32m2_t mask_f32 = __riscv_vfwcvt_f_f_v_f32m2(
      __riscv_vle16_v_f16m1(mask, vl), vl);
  score4 = __riscv_vfadd_vv_f32m2(
      __riscv_vfmul_vf_f32m2(score4, scale, vl), mask_f32, vl);
  score5 = __riscv_vfadd_vv_f32m2(
      __riscv_vfmul_vf_f32m2(score5, scale, vl), mask_f32, vl);
  __riscv_vse32_v_f32m2(attention_tiled_score[4], score4, vl);
  __riscv_vse32_v_f32m2(attention_tiled_score[5], score5, vl);
}

static __attribute__((noinline)) void softmax_tiled_scores_rvv(
    int tile_tokens) {
  const size_t vl = __riscv_vsetvl_e32m2(tile_tokens);
#pragma clang loop unroll(disable)
  for (int head = 0; head < TILED_RVV_Q_ROWS; ++head) {
    vfloat32m2_t scores =
        __riscv_vle32_v_f32m2(attention_tiled_score[head], vl);
    const float tile_maximum = reduce_max_f32m2(scores, vl);
    const float old_maximum = attention_tiled_maximum[head];
    const float new_maximum =
        tile_maximum > old_maximum ? tile_maximum : old_maximum;
    const float old_scale = old_maximum == negative_infinity_f32()
                                ? 0.0f
                                : expf(old_maximum - new_maximum);
    scores = vector_expf(
        __riscv_vfsub_vf_f32m2(scores, new_maximum, vl), vl);
    attention_tiled_sum[head] =
        attention_tiled_sum[head] * old_scale +
        reduce_sum_f32m2(scores, vl);
    attention_tiled_maximum[head] = new_maximum;
    attention_tiled_old_scale[head] = old_scale;
    __riscv_vse32_v_f32m2(attention_tiled_score[head], scores, vl);
  }
}

static __attribute__((noinline)) void softmax_tiled_scores4_rvv(
    int tile_tokens) {
  const size_t vl = __riscv_vsetvl_e32m2(tile_tokens);
#pragma clang loop unroll(disable)
  for (int head = 0; head < 4; ++head) {
    vfloat32m2_t scores =
        __riscv_vle32_v_f32m2(attention_tiled_score[head], vl);
    const float tile_maximum = reduce_max_f32m2(scores, vl);
    const float old_maximum = attention_tiled_maximum[head];
    const float new_maximum =
        tile_maximum > old_maximum ? tile_maximum : old_maximum;
    const float old_scale = old_maximum == negative_infinity_f32()
                                ? 0.0f
                                : expf(old_maximum - new_maximum);
    scores = vector_expf(
        __riscv_vfsub_vf_f32m2(scores, new_maximum, vl), vl);
    attention_tiled_sum[head] =
        attention_tiled_sum[head] * old_scale + reduce_sum_f32m2(scores, vl);
    attention_tiled_maximum[head] = new_maximum;
    attention_tiled_old_scale[head] = old_scale;
    __riscv_vse32_v_f32m2(attention_tiled_score[head], scores, vl);
  }
}

static void update_tiled_outputs_rvv(int dim, int tile_tokens) {
  const size_t vl = __riscv_vsetvl_e16m2(dim);
  vfloat16m2_t accum0 = __riscv_vfmul_vf_f16m2(
      __riscv_vle16_v_f16m2(attention_tiled_accum[0], vl),
      (_Float16)attention_tiled_old_scale[0], vl);
  vfloat16m2_t accum1 = __riscv_vfmul_vf_f16m2(
      __riscv_vle16_v_f16m2(attention_tiled_accum[1], vl),
      (_Float16)attention_tiled_old_scale[1], vl);
  vfloat16m2_t accum2 = __riscv_vfmul_vf_f16m2(
      __riscv_vle16_v_f16m2(attention_tiled_accum[2], vl),
      (_Float16)attention_tiled_old_scale[2], vl);
  vfloat16m2_t accum3 = __riscv_vfmul_vf_f16m2(
      __riscv_vle16_v_f16m2(attention_tiled_accum[3], vl),
      (_Float16)attention_tiled_old_scale[3], vl);
  vfloat16m2_t accum4 = __riscv_vfmul_vf_f16m2(
      __riscv_vle16_v_f16m2(attention_tiled_accum[4], vl),
      (_Float16)attention_tiled_old_scale[4], vl);
  vfloat16m2_t accum5 = __riscv_vfmul_vf_f16m2(
      __riscv_vle16_v_f16m2(attention_tiled_accum[5], vl),
      (_Float16)attention_tiled_old_scale[5], vl);

  for (int token = 0; token < tile_tokens; ++token) {
    const vfloat16m2_t value =
        __riscv_vle16_v_f16m2(attention_tiled_value[token], vl);
    accum0 = __riscv_vfmacc_vf_f16m2(
        accum0, (_Float16)attention_tiled_score[0][token], value, vl);
    accum1 = __riscv_vfmacc_vf_f16m2(
        accum1, (_Float16)attention_tiled_score[1][token], value, vl);
    accum2 = __riscv_vfmacc_vf_f16m2(
        accum2, (_Float16)attention_tiled_score[2][token], value, vl);
    accum3 = __riscv_vfmacc_vf_f16m2(
        accum3, (_Float16)attention_tiled_score[3][token], value, vl);
    accum4 = __riscv_vfmacc_vf_f16m2(
        accum4, (_Float16)attention_tiled_score[4][token], value, vl);
    accum5 = __riscv_vfmacc_vf_f16m2(
        accum5, (_Float16)attention_tiled_score[5][token], value, vl);
  }

  __riscv_vse16_v_f16m2(attention_tiled_accum[0], accum0, vl);
  __riscv_vse16_v_f16m2(attention_tiled_accum[1], accum1, vl);
  __riscv_vse16_v_f16m2(attention_tiled_accum[2], accum2, vl);
  __riscv_vse16_v_f16m2(attention_tiled_accum[3], accum3, vl);
  __riscv_vse16_v_f16m2(attention_tiled_accum[4], accum4, vl);
  __riscv_vse16_v_f16m2(attention_tiled_accum[5], accum5, vl);
}

static inline vfloat16m2_t scale_f16_state_f32(
    vfloat16m2_t accumulator, float factor, size_t vl) {
  return __riscv_vfncvt_f_f_w_f16m2(
      __riscv_vfmul_vf_f32m4(
          __riscv_vfwcvt_f_f_v_f32m4(accumulator, vl), factor, vl),
      vl);
}

static inline vfloat16m2_t update_f16_state_f32(
    vfloat16m2_t accumulator, float weight, vfloat32m4_t value,
    size_t vl) {
  return __riscv_vfncvt_f_f_w_f16m2(
      __riscv_vfmacc_vf_f32m4(
          __riscv_vfwcvt_f_f_v_f32m4(accumulator, vl), weight, value, vl),
      vl);
}

static void update_tiled_outputs4_d256_rvv(int tile_tokens) {
  for (int offset = 0; offset < AKV_HEAD_DIM_256;) {
    const size_t vl =
        __riscv_vsetvl_e16m2(AKV_HEAD_DIM_256 - offset);
    vfloat16m2_t accum0 = scale_f16_state_f32(
        __riscv_vle16_v_f16m2(attention_tiled_accum[0] + offset, vl),
        attention_tiled_old_scale[0], vl);
    vfloat16m2_t accum1 = scale_f16_state_f32(
        __riscv_vle16_v_f16m2(attention_tiled_accum[1] + offset, vl),
        attention_tiled_old_scale[1], vl);
    vfloat16m2_t accum2 = scale_f16_state_f32(
        __riscv_vle16_v_f16m2(attention_tiled_accum[2] + offset, vl),
        attention_tiled_old_scale[2], vl);
    vfloat16m2_t accum3 = scale_f16_state_f32(
        __riscv_vle16_v_f16m2(attention_tiled_accum[3] + offset, vl),
        attention_tiled_old_scale[3], vl);

    for (int token = 0; token < tile_tokens; ++token) {
      const vfloat32m4_t value = __riscv_vfwcvt_f_f_v_f32m4(
          __riscv_vle16_v_f16m2(
              attention_tiled_value[token] + offset, vl),
          vl);
      accum0 = update_f16_state_f32(
          accum0, attention_tiled_score[0][token], value, vl);
      accum1 = update_f16_state_f32(
          accum1, attention_tiled_score[1][token], value, vl);
      accum2 = update_f16_state_f32(
          accum2, attention_tiled_score[2][token], value, vl);
      accum3 = update_f16_state_f32(
          accum3, attention_tiled_score[3][token], value, vl);
    }

    __riscv_vse16_v_f16m2(attention_tiled_accum[0] + offset, accum0, vl);
    __riscv_vse16_v_f16m2(attention_tiled_accum[1] + offset, accum1, vl);
    __riscv_vse16_v_f16m2(attention_tiled_accum[2] + offset, accum2, vl);
    __riscv_vse16_v_f16m2(attention_tiled_accum[3] + offset, accum3, vl);
    offset += (int)vl;
  }
}

static void store_tiled_outputs_rvv(float *output, int dim) {
  for (int head = 0; head < TILED_RVV_Q_ROWS; ++head) {
    const float inverse = attention_tiled_sum[head] == 0.0f
                              ? 0.0f
                              : 1.0f / attention_tiled_sum[head];
    for (int offset = 0; offset < dim;) {
      const size_t vl = __riscv_vsetvl_e16m2(dim - offset);
      const vfloat16m2_t accum = __riscv_vle16_v_f16m2(
          attention_tiled_accum[head] + offset, vl);
      const vfloat32m4_t result = __riscv_vfmul_vf_f32m4(
          __riscv_vfwcvt_f_f_v_f32m4(accum, vl), inverse, vl);
      __riscv_vse32_v_f32m4(
          output + (size_t)head * dim + offset, result, vl);
      offset += (int)vl;
    }
  }
}

static void store_tiled_outputs4_d256_rvv(float *output) {
  for (int head = 0; head < 4; ++head) {
    const float inverse = attention_tiled_sum[head] == 0.0f
                              ? 0.0f
                              : 1.0f / attention_tiled_sum[head];
    for (int offset = 0; offset < AKV_HEAD_DIM_256;) {
      const size_t vl =
          __riscv_vsetvl_e16m2(AKV_HEAD_DIM_256 - offset);
      const vfloat32m4_t result = __riscv_vfmul_vf_f32m4(
          __riscv_vfwcvt_f_f_v_f32m4(
              __riscv_vle16_v_f16m2(
                  attention_tiled_accum[head] + offset, vl),
              vl),
          inverse, vl);
      __riscv_vse32_v_f32m4(
          output + (size_t)head * AKV_HEAD_DIM_256 + offset, result, vl);
      offset += (int)vl;
    }
  }
}

// Returns zero for shapes outside this deliberately strict strong-baseline
// profile. The caller then preserves the standard one-row RVV fallback.
static int run_attention_tiled_rvv(const case_config_t *cfg) {
  const float *query = (const float *)llama_input_a_start;
  const _Float16 *key = (const _Float16 *)llama_input_b_start;
  const _Float16 *value = (const _Float16 *)llama_input_c_start;
  const uint16_t *mask_bits = (const uint16_t *)llama_input_d_start;
  const _Float16 *mask = (const _Float16 *)llama_input_d_start;
  const int dim = cfg->args[0];
  const int tokens = cfg->args[1];
  const int qheads = cfg->args[2];
  const int physical_kvlen = cfg->args[3];
  const int kvheads = cfg->args[4];
  const int heads_per_kv = qheads / kvheads;
  const int active_kv = attention_active_prefix(mask_bits, physical_kvlen);
  const size_t token_tile_vl =
      __riscv_vsetvl_e16m1(TILED_RVV_KV_TILE);
  const int d128_gqa6 =
      dim == TILED_RVV_DIM && heads_per_kv == TILED_RVV_Q_ROWS;
  const int d256_gqa4 =
      dim == AKV_HEAD_DIM_256 && heads_per_kv == 4;

  if ((!d128_gqa6 && !d256_gqa4) || tokens != 1 || active_kv <= 0 ||
      token_tile_vl != TILED_RVV_KV_TILE)
    return 0;

  for (int kvhead = 0; kvhead < kvheads; ++kvhead) {
    const int first_qhead = kvhead * heads_per_kv;
    HW_CNT_PHASE(ATTENTION_PHASE_Q_CONVERT);
    if (d256_gqa4)
      prepare_tiled_query4_d256_rvv(
          query + (size_t)first_qhead * dim);
    else
      prepare_tiled_query_rvv(
          query + (size_t)first_qhead * dim, dim);

    for (int tile_start = 0; tile_start < active_kv;
         tile_start += TILED_RVV_KV_TILE) {
      int tile_tokens = active_kv - tile_start;
      if (tile_tokens > TILED_RVV_KV_TILE)
        tile_tokens = TILED_RVV_KV_TILE;

      const size_t kv_base =
          ((size_t)kvhead * physical_kvlen + tile_start) * dim;
      HW_CNT_PHASE(ATTENTION_PHASE_ONLINE_KV);
      pack_tiled_kv_rvv(key + kv_base, value + kv_base,
                        dim, tile_tokens);

      HW_CNT_PHASE(ATTENTION_PHASE_OUTPUT);
      compute_tiled_scores4_rvv(cfg->params[2], mask + tile_start,
                                dim, tile_tokens);
      if (d256_gqa4) {
        softmax_tiled_scores4_rvv(tile_tokens);
        update_tiled_outputs4_d256_rvv(tile_tokens);
      } else {
        compute_tiled_scores2_rvv(cfg->params[2], mask + tile_start,
                                  dim, tile_tokens);
        softmax_tiled_scores_rvv(tile_tokens);
        update_tiled_outputs_rvv(dim, tile_tokens);
      }
    }

    HW_CNT_PHASE(ATTENTION_PHASE_OUTPUT);
    if (d256_gqa4)
      store_tiled_outputs4_d256_rvv(
          attention_output + (size_t)first_qhead * dim);
    else
      store_tiled_outputs_rvv(
          attention_output + (size_t)first_qhead * dim, dim);
  }
  return 1;
}

// Returns zero when the shape or mask is outside the version-1 AKV contract;
// the caller then executes the unchanged standard RVV implementation.
static int run_attention_akv(const case_config_t *cfg) {
  const float *query = (const float *)llama_input_a_start;
  const _Float16 *key = (const _Float16 *)llama_input_b_start;
  const _Float16 *value = (const _Float16 *)llama_input_c_start;
  const uint16_t *mask = (const uint16_t *)llama_input_d_start;
  const int dim = cfg->args[0];
  const int tokens = cfg->args[1];
  const int qheads = cfg->args[2];
  const int physical_kvlen = cfg->args[3];
  const int kvheads = cfg->args[4];
  const int heads_per_kv = qheads / kvheads;
  const int active_kv = attention_active_prefix(mask, physical_kvlen);

  if (dim != AKV_HEAD_DIM_128 || tokens != 1 ||
      heads_per_kv != 6 || active_kv <= 0 || active_kv > UINT16_MAX)
    return 0;

  for (int kvhead = 0; kvhead < kvheads; ++kvhead) {
    const int first_qhead = kvhead * heads_per_kv;
    HW_CNT_PHASE(ATTENTION_PHASE_Q_CONVERT);
    for (int head = 0; head < heads_per_kv; ++head) {
      convert_f32_to_f16_rvv(
          attention_query_group_f16 + (size_t)head * dim,
          query + (size_t)(first_qhead + head) * dim, dim);
    }

    const akv_attention_problem_t problem = {
        .query = (const uint16_t *)attention_query_group_f16,
        .key = (const uint16_t *)(
            key + (size_t)kvhead * physical_kvlen * dim),
        .value = (const uint16_t *)(
            value + (size_t)kvhead * physical_kvlen * dim),
        .mask = mask,
        .output = attention_output + (size_t)first_qhead * dim,
        .q_row_stride_bytes = (uint32_t)dim * sizeof(_Float16),
        .k_token_stride_bytes = (uint32_t)dim * sizeof(_Float16),
        .v_token_stride_bytes = (uint32_t)dim * sizeof(_Float16),
        .output_row_stride_bytes = (uint32_t)dim * sizeof(float),
        .q_rows = (uint32_t)heads_per_kv,
        .head_dim = (uint32_t)dim,
        .kv_length = (uint32_t)active_kv,
        .scale = cfg->params[2],
    };
    if (akv_attention_plan_create(&attention_akv_device, &problem,
                                  &attention_akv_plan) !=
            AKV_STATUS_OK)
      return 0;

    HW_CNT_PHASE(ATTENTION_PHASE_ONLINE_KV);
    if (akv_attention_execute_native(&attention_akv_plan) != AKV_STATUS_OK)
      return 0;
  }
  return 1;
}

// AKV-v2 supplies token-axis K columns and row-major V rows. The score,
// softmax, and output arithmetic remains the same standard-RVV schedule used
// by the measured tiled baseline, but no software K/V packing is performed.
static int run_attention_akv_v2(const case_config_t *cfg) {
  const float *query = (const float *)llama_input_a_start;
  const _Float16 *key = (const _Float16 *)llama_input_b_start;
  const _Float16 *value = (const _Float16 *)llama_input_c_start;
  const uint16_t *mask = (const uint16_t *)llama_input_d_start;
  const int dim = cfg->args[0];
  const int tokens = cfg->args[1];
  const int qheads = cfg->args[2];
  const int physical_kvlen = cfg->args[3];
  const int kvheads = cfg->args[4];
  const int heads_per_kv = qheads / kvheads;

  if (!akv_attention_v2_shape_supported((uint32_t)heads_per_kv,
                                        (uint32_t)dim) ||
      !attention_akv_device.capabilities.token_axis_valid)
    return 0;

  for (int token = 0; token < tokens; ++token) {
    const uint16_t *token_mask = mask + (size_t)token * physical_kvlen;
    const int active_kv = attention_active_prefix(token_mask, physical_kvlen);
    if (active_kv <= 0 || active_kv > UINT16_MAX) return 0;

    for (int kvhead = 0; kvhead < kvheads; ++kvhead) {
      const int first_qhead = kvhead * heads_per_kv;
      HW_CNT_PHASE(ATTENTION_PHASE_Q_CONVERT);
      for (int head = 0; head < heads_per_kv; ++head) {
        const size_t query_index =
            ((size_t)(first_qhead + head) * tokens + token) * dim;
        convert_f32_to_f16_rvv(
            attention_query_group_f16 + (size_t)head * dim,
            query + query_index, dim);
      }

      const akv_attention_problem_t problem = {
          .query = (const uint16_t *)attention_query_group_f16,
          .key = (const uint16_t *)(
              key + (size_t)kvhead * physical_kvlen * dim),
          .value = (const uint16_t *)(
              value + (size_t)kvhead * physical_kvlen * dim),
          .mask = token_mask,
          .output = attention_output +
                    ((size_t)token * qheads + first_qhead) * dim,
          .q_row_stride_bytes = (uint32_t)dim * sizeof(_Float16),
          .k_token_stride_bytes = (uint32_t)dim * sizeof(_Float16),
          .v_token_stride_bytes = (uint32_t)dim * sizeof(_Float16),
          .output_row_stride_bytes = (uint32_t)dim * sizeof(float),
          .q_rows = (uint32_t)heads_per_kv,
          .head_dim = (uint32_t)dim,
          .kv_length = (uint32_t)active_kv,
          .scale = cfg->params[2],
      };
      if (akv_attention_plan_create_v2(&attention_akv_device, &problem,
                                       &attention_akv_plan) != AKV_STATUS_OK)
        return 0;

      HW_CNT_PHASE(ATTENTION_PHASE_ONLINE_KV);
      if (akv_attention_execute_v2_native(&attention_akv_plan,
                                          &attention_akv_v2_workspace) !=
          AKV_STATUS_OK)
        return 0;
    }
  }
  return 1;
}

static void run_attention_rvv(const case_config_t *cfg) {
  const float *query = (const float *)llama_input_a_start;
  const _Float16 *key = (const _Float16 *)llama_input_b_start;
  const _Float16 *value = (const _Float16 *)llama_input_c_start;
  const uint16_t *mask = (const uint16_t *)llama_input_d_start;
  const int dim = cfg->args[0];
  const int tokens = cfg->args[1];
  const int qheads = cfg->args[2];
  const int kvlen = cfg->args[3];
  const int kvheads = cfg->args[4];
  const int heads_per_kv = qheads / kvheads;

  for (int qhead = 0; qhead < qheads; ++qhead) {
    const int kvhead = qhead / heads_per_kv;
    for (int token = 0; token < tokens; ++token) {
      const float *q = query + ((size_t)qhead * tokens + token) * dim;
      HW_CNT_PHASE(ATTENTION_PHASE_Q_CONVERT);
      convert_f32_to_f16_rvv(attention_query_f16, q, dim);
      clear_attention_accum_rvv(dim);

      float sum_weights = 0.0f;
      float maximum = negative_infinity_f32();
      HW_CNT_PHASE(ATTENTION_PHASE_ONLINE_KV);
      for (int sequence = 0; sequence < kvlen; ++sequence) {
        const uint16_t mask_bits = mask[(size_t)token * kvlen + sequence];
        if (mask_bits == 0xfc00u) continue;

        const _Float16 *k = key + ((size_t)kvhead * kvlen + sequence) * dim;
        const float score = dot_f16_rvv(k, attention_query_f16, dim) *
                                cfg->params[2] +
                            fp16_to_fp32(mask_bits);
        const float old_maximum = maximum;
        float old_scale = 1.0f;
        float weight = 1.0f;
        if (score > maximum) {
          maximum = score;
          old_scale = expf(old_maximum - maximum);
          if (dim == AKV_HEAD_DIM_256)
            scale_attention_accum_rvv_f32_weight(old_scale, dim);
          else
            scale_attention_accum_rvv(old_scale, dim);
        } else {
          weight = expf(score - maximum);
        }
        const _Float16 *v = value + ((size_t)kvhead * kvlen + sequence) * dim;
        if (dim == AKV_HEAD_DIM_256)
          mad_attention_accum_rvv_f32_weight(v, weight, dim);
        else
          mad_attention_accum_rvv(v, weight, dim);
        sum_weights = sum_weights * old_scale + weight;
      }

      HW_CNT_PHASE(ATTENTION_PHASE_OUTPUT);
      const float inverse = sum_weights == 0.0f ? 0.0f : 1.0f / sum_weights;
      const size_t output_index = ((size_t)token * qheads + qhead) * dim;
      store_attention_output_rvv(attention_output + output_index, inverse, dim);
    }
  }
}

static int check_attention(const case_config_t *cfg) {
  const float *golden = (const float *)llama_golden_start;
  const size_t count = (size_t)cfg->args[0] * cfg->args[1] * cfg->args[2];
  int failures_by_head[MAX_ATTENTION_HEADS] = {0};
  int failures = 0;
  for (size_t item = 0; item < count; ++item) {
    if (!close_f32(attention_output[item], golden[item],
                   cfg->params[0], cfg->params[1])) {
      const size_t head = (item / (size_t)cfg->args[0]) % cfg->args[2];
      uint32_t actual_bits;
      uint32_t golden_bits;
      __builtin_memcpy(&actual_bits, &attention_output[item], sizeof(actual_bits));
      __builtin_memcpy(&golden_bits, &golden[item], sizeof(golden_bits));
      if (failures < 12) {
        REPORT("ATTENTION_MISMATCH item=%lu head=%lu element=%lu "
               "actual=0x%08x golden=0x%08x\n",
               (unsigned long)item, (unsigned long)head,
               (unsigned long)(item % cfg->args[0]), actual_bits, golden_bits);
#if defined(SPIKE) && defined(SPIKE_DIAGNOSTICS)
        printstr("ATTENTION_MISMATCH item=0x");
        printhex(item);
        printstr(" head=0x");
        printhex(head);
        printstr(" element=0x");
        printhex(item % cfg->args[0]);
        printstr(" actual=0x");
        printhex(actual_bits);
        printstr(" golden=0x");
        printhex(golden_bits);
        printstr("\n");
#endif
      }
      ++failures_by_head[head];
      ++failures;
    }
  }
  if (failures != 0) {
    for (size_t head = 0; head < cfg->args[2]; ++head) {
      if (failures_by_head[head] != 0) {
        REPORT("ATTENTION_MISMATCH_HEAD head=%lu mismatches=%d\n",
               (unsigned long)head, failures_by_head[head]);
      }
    }
  }
  return failures;
}

int main(void) {
  const case_config_t *cfg = &llama_case_config;
  if (cfg->magic != 0x514b4d4f || cfg->version != 1) return 1;
  if (cfg->kind != CASE_ATTENTION &&
      operator_element_count(cfg) > MAX_OPERATOR_ELEMENTS)
    return 1;
  if (!operator_config_is_valid(cfg)) return 1;
  if (cfg->kind == CASE_ATTENTION && !attention_shape_is_supported(cfg)) return 1;
  if (cfg->kind == CASE_ATTENTION &&
      (cfg->flags & (CASE_FLAG_ATTENTION_AKV |
                     CASE_FLAG_ATTENTION_AKV_V2)) != 0 &&
      akv_device_init_reference(&attention_akv_device) != AKV_STATUS_OK)
    return 1;
  HW_CNT_READY;
  perf_time();
  const uint64_t start = read_cycle();
  int failures = 0;
  switch (cfg->kind) {
    case CASE_LINEAR_Q4:
    case CASE_LINEAR_Q6: run_linear(cfg); break;
    case CASE_ADD: run_add(cfg); break;
    case CASE_SILU_MUL: run_silu_mul(cfg); break;
    case CASE_RMS_NORM: run_rms_norm(cfg); break;
    case CASE_ROPE: run_rope(cfg); break;
    case CASE_SET_ROWS_F32_F16: run_set_rows_f32_f16(cfg); break;
    case CASE_GET_ROWS_F32: run_get_rows_f32(cfg); break;
    case CASE_GET_ROWS_Q4_K: run_get_rows_q4_k(cfg); break;
    case CASE_ATTENTION:
      if ((cfg->flags & CASE_FLAG_ATTENTION_AKV_V2) != 0) {
        if (!run_attention_akv_v2(cfg)) run_attention_rvv(cfg);
      } else if ((cfg->flags & CASE_FLAG_ATTENTION_AKV) != 0) {
        if (!run_attention_akv(cfg)) run_attention_rvv(cfg);
      } else if ((cfg->flags & CASE_FLAG_ATTENTION_TILED_RVV) != 0) {
        if (!run_attention_tiled_rvv(cfg)) run_attention_rvv(cfg);
      } else if ((cfg->flags & CASE_FLAG_ATTENTION_RVV) != 0) {
        run_attention_rvv(cfg);
      } else {
        run_attention_reference(cfg);
      }
      failures = 0;
      break;
    default: return 1;
  }
  const uint64_t cycles = read_cycle() - start;
  perf_time();
  HW_CNT_NOT_READY;
  if (cfg->kind == CASE_ATTENTION) {
    failures = check_attention(cfg);
  } else if (cfg->kind == CASE_SET_ROWS_F32_F16) {
    failures = check_set_rows(cfg);
  } else {
    failures = check_operator(cfg);
  }
  REPORT("LLAMA_OPERATOR %s %s cycles=%lu mismatches=%d\n", llama_case_name,
         failures == 0 ? "PASS" : "FAIL", (unsigned long)cycles, failures);
  return failures == 0 ? 0 : 1;
}
