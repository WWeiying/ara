#include "../llama_q4km_micro/micro_kernels.h"

#include <math.h>
#include <riscv_vector.h>
#include <stddef.h>
#include <stdint.h>

#include "runtime.h"

#ifdef SPIKE
#define REPORT(...) do { } while (0)
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
};

enum {
  CASE_FLAG_ATTENTION_RVV = 1u << 0,
  ATTENTION_PHASE_Q_CONVERT = 1,
  ATTENTION_PHASE_ONLINE_KV = 2,
  ATTENTION_PHASE_OUTPUT = 3,
  MAX_ATTENTION_DIM = 128,
  MAX_ATTENTION_TOKENS = 15,
  MAX_ATTENTION_HEADS = 12,
  MAX_ATTENTION_KV = 256,
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
static float attention_output[MAX_ATTENTION_DIM * MAX_ATTENTION_TOKENS *
                              MAX_ATTENTION_HEADS];
static _Float16 attention_query_f16[MAX_ATTENTION_DIM];
static _Float16 attention_accum_f16[MAX_ATTENTION_DIM];

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

static vfloat32m2_t vector_expf(vfloat32m2_t x, size_t vl) {
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

static int run_linear(const case_config_t *cfg) {
  const int k = cfg->args[0];
  const int output_rows = cfg->args[1];
  const int columns = cfg->args[2];
  const float *activation = (const float *)llama_input_b_start;
  const float *golden = (const float *)llama_golden_start;
  const int blocks = k / QK_K;
  int failures = 0;

  for (int column = 0; column < columns; ++column) {
    q4km_quantize_row_q8_K(activation + (size_t)column * k, quantized, k);
    for (int row = 0; row < output_rows; ++row) {
      float actual;
      if (cfg->kind == CASE_LINEAR_Q4) {
        actual = q4km_vec_dot_q4_K_q8_K(
            (const block_q4_K *)llama_input_a_start + (size_t)row * blocks,
            quantized, k);
      } else {
        actual = q4km_vec_dot_q6_K_q8_K(
            (const block_q6_K *)llama_input_a_start + (size_t)row * blocks,
            quantized, k);
      }
      if (!close_f32(actual, golden[(size_t)column * output_rows + row],
                     cfg->params[0], cfg->params[1])) {
        ++failures;
      }
    }
  }
  return failures;
}

static int run_add(const case_config_t *cfg) {
  const float *a = (const float *)llama_input_a_start;
  const float *b = (const float *)llama_input_b_start;
  const float *golden = (const float *)llama_golden_start;
  const size_t count = cfg->args[0];
  int failures = 0;
  for (size_t offset = 0; offset < count;) {
    const size_t vl = __riscv_vsetvl_e32m8(count - offset);
    const vfloat32m8_t result = __riscv_vfadd_vv_f32m8(
        __riscv_vle32_v_f32m8(a + offset, vl),
        __riscv_vle32_v_f32m8(b + offset, vl), vl);
    __riscv_vse32_v_f32m8(scratch, result, vl);
    for (size_t item = 0; item < vl; ++item) {
      failures += !close_f32(scratch[item], golden[offset + item],
                             cfg->params[0], cfg->params[1]);
    }
    offset += vl;
  }
  return failures;
}

static int run_silu_mul(const case_config_t *cfg) {
  const float *a = (const float *)llama_input_a_start;
  const float *b = (const float *)llama_input_b_start;
  const float *golden = (const float *)llama_golden_start;
  const size_t count = cfg->args[0];
  int failures = 0;
  for (size_t offset = 0; offset < count;) {
    const size_t vl = __riscv_vsetvl_e32m2(count - offset);
    const vfloat32m2_t x = __riscv_vle32_v_f32m2(a + offset, vl);
    const vfloat32m2_t denominator = __riscv_vfadd_vf_f32m2(
        vector_expf(__riscv_vfneg_v_f32m2(x, vl), vl), 1.0f, vl);
    const vfloat32m2_t silu = __riscv_vfdiv_vv_f32m2(x, denominator, vl);
    const vfloat32m2_t result = __riscv_vfmul_vv_f32m2(
        silu, __riscv_vle32_v_f32m2(b + offset, vl), vl);
    __riscv_vse32_v_f32m2(scratch, result, vl);
    for (size_t item = 0; item < vl; ++item) {
      failures += !close_f32(scratch[item], golden[offset + item],
                             cfg->params[0], cfg->params[1]);
    }
    offset += vl;
  }
  return failures;
}

static int run_rms_norm(const case_config_t *cfg) {
  const float *input = (const float *)llama_input_a_start;
  const float *weight = (const float *)llama_input_b_start;
  const float *golden = (const float *)llama_golden_start;
  const int width = cfg->args[0];
  const int rows = cfg->args[1];
  int failures = 0;

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
      __riscv_vse32_v_f32m8(scratch, result, vl);
      for (size_t item = 0; item < vl; ++item) {
        failures += !close_f32(
            scratch[item], golden[(size_t)row * width + offset + item],
            cfg->params[0], cfg->params[1]);
      }
      offset += vl;
    }
  }
  return failures;
}

static int run_rope(const case_config_t *cfg) {
  const float *input = (const float *)llama_input_a_start;
  const int32_t *position = (const int32_t *)llama_input_b_start;
  const float *golden = (const float *)llama_golden_start;
  const int n_dims = cfg->args[0];
  const int mode = cfg->args[1];
  const int width = cfg->args[2];
  const int heads = cfg->args[3];
  const int tokens = cfg->args[4];
  const float theta_scale = powf(cfg->params[2], -2.0f / n_dims);
  int failures = 0;

  if (mode != 2 || width != n_dims) return 1;
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
        failures += !close_f32(x0 * c - x1 * s, golden[base + pair],
                               cfg->params[0], cfg->params[1]);
        failures += !close_f32(x0 * s + x1 * c,
                               golden[base + pair + n_dims / 2],
                               cfg->params[0], cfg->params[1]);
      }
    }
  }
  return failures;
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

static void convert_query_f32_to_f16_rvv(const float *query, int count) {
  for (int offset = 0; offset < count;) {
    const size_t vl = __riscv_vsetvl_e32m4(count - offset);
    const vfloat32m4_t values = __riscv_vle32_v_f32m4(query + offset, vl);
    __riscv_vse16_v_f16m2(
        attention_query_f16 + offset,
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
      convert_query_f32_to_f16_rvv(q, dim);
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
          scale_attention_accum_rvv(old_scale, dim);
        } else {
          weight = expf(score - maximum);
        }
        const _Float16 *v = value + ((size_t)kvhead * kvlen + sequence) * dim;
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
  int failures = 0;
  for (size_t item = 0; item < count; ++item) {
    failures += !close_f32(attention_output[item], golden[item],
                           cfg->params[0], cfg->params[1]);
  }
  return failures;
}

int main(void) {
  const case_config_t *cfg = &llama_case_config;
  if (cfg->magic != 0x514b4d4f || cfg->version != 1) return 1;
  if (cfg->kind == CASE_ATTENTION && !attention_shape_is_supported(cfg)) return 1;
  HW_CNT_READY;
  perf_time();
  const uint64_t start = read_cycle();
  int failures;
  switch (cfg->kind) {
    case CASE_LINEAR_Q4:
    case CASE_LINEAR_Q6: failures = run_linear(cfg); break;
    case CASE_ADD: failures = run_add(cfg); break;
    case CASE_SILU_MUL: failures = run_silu_mul(cfg); break;
    case CASE_RMS_NORM: failures = run_rms_norm(cfg); break;
    case CASE_ROPE: failures = run_rope(cfg); break;
    case CASE_ATTENTION:
      if ((cfg->flags & CASE_FLAG_ATTENTION_RVV) != 0) {
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
  if (cfg->kind == CASE_ATTENTION) failures = check_attention(cfg);
  REPORT("LLAMA_OPERATOR %s %s cycles=%lu mismatches=%d\n", llama_case_name,
         failures == 0 ? "PASS" : "FAIL", (unsigned long)cycles, failures);
  return failures == 0 ? 0 : 1;
}
