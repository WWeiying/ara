#include <stdint.h>
#include <string.h>
#include <riscv_vector.h>
#include "printf.h"
#include "../../software/akv/include/akv/akv.h"

enum { HEADS = 8, STRIDE = 288, DIM = 256, TOKENS = 65, TILE = 64 };
extern const uint16_t query[HEADS][STRIDE];
extern const uint16_t key[TOKENS][STRIDE];
extern const uint16_t value[TOKENS][STRIDE];
extern const uint16_t initial_accum[HEADS][DIM];
extern const float weights[HEADS][TILE];
extern const float old_scale[HEADS];
extern const float token_scale[HEADS][TILE];
extern const float online_weights[HEADS][TILE];
static uint16_t mask[TOKENS] __attribute__((aligned(64)));
static float output[HEADS][DIM] __attribute__((aligned(64)));
static float scores[HEADS][TILE] __attribute__((aligned(64)));
static float reference_scores[HEADS][TILE] __attribute__((aligned(64)));
static uint16_t accum[HEADS][DIM] __attribute__((aligned(64)));
static uint16_t reference_accum[HEADS][DIM] __attribute__((aligned(64)));

extern void akv_v2_compute_scores_f16_d256_generic(
    const uint16_t *, float *, uint32_t, size_t, uint32_t);
extern void akv_v2_compute_scores_f16_d256_panel4(
    const uint16_t *, float *, uint32_t, size_t, uint32_t);
extern void akv_v2_update_outputs_f16_d256_generic(
    const float *, uint16_t *, const float *, uint32_t, uint32_t);
extern void akv_v2_update_outputs_f16_d256_online(
    const float *, uint16_t *, const float *, uint32_t, uint32_t);
extern void akv_d256_scores_reference(
    const uint16_t *, float *, uint32_t, size_t, uint32_t);
extern void akv_d256_outputs_reference(
    const float *, uint16_t *, const float *, uint32_t, uint32_t);

static void fill(const akv_descriptor_t *descriptor, unsigned first) {
  __asm__ volatile("fence rw,rw\n.insn r 0x5b,6,0,x0,%0,%1"
                   : : "r"(descriptor), "r"((uintptr_t)first) : "memory");
}

static unsigned flags(void) {
  uintptr_t value;
  __asm__ volatile("csrr %0, fflags" : "=r"(value) : : "memory");
  return (unsigned)value;
}

static void clear_flags(void) {
  __asm__ volatile("csrw fflags, zero" : : : "memory");
}

/* Independent RVV-memory oracle: no AKV row delivery and no assembly helper. */
static void online_reference(unsigned rows, unsigned tokens, unsigned first) {
  for (unsigned head = 0; head < rows; ++head) {
    for (unsigned offset = 0; offset < DIM;) {
      const size_t vl = __riscv_vsetvl_e16m2(DIM - offset);
      vfloat16m2_t result = __riscv_vle16_v_f16m2(
          (const _Float16 *)reference_accum[head] + offset, vl);
      for (unsigned token = 0; token < tokens; ++token) {
        const float scale = token_scale[head][token];
        if (scale != 1.0f)
          result = __riscv_vfncvt_f_f_w_f16m2(__riscv_vfmul_vf_f32m4(
              __riscv_vfwcvt_f_f_v_f32m4(result, vl), scale, vl), vl);
        const float weight = online_weights[head][token];
        if (weight != 0.0f) {
          const vfloat16m2_t row = __riscv_vle16_v_f16m2(
              (const _Float16 *)value[first + token] + offset, vl);
          result = __riscv_vfncvt_f_f_w_f16m2(__riscv_vfmacc_vf_f32m4(
              __riscv_vfwcvt_f_f_v_f32m4(result, vl), weight,
              __riscv_vfwcvt_f_f_v_f32m4(row, vl), vl), vl);
        }
      }
      __riscv_vse16_v_f16m2((_Float16 *)reference_accum[head] + offset, result, vl);
      offset += (unsigned)vl;
    }
  }
}

int main(void) {
  akv_device_t device;
  if (akv_device_query(akv_native_info, 0, &device) != AKV_STATUS_OK) return 1;
  printf("AKV_D256_REUSE start preloaded_inputs=1\n");

  const struct { unsigned rows, kv, first, rounding; } cases[] = {
      {1, 1, 0, 0}, {3, 17, 0, 0}, {4, 17, 0, 0}, {5, 65, 64, 0},
      {7, 3, 0, 0}, {8, 65, 0, 0}, {8, 65, 64, 0}, {4, 1, 0, 2},
  };
  for (unsigned test = 0; test < sizeof(cases) / sizeof(cases[0]); ++test) {
    const unsigned rows = cases[test].rows;
    const unsigned tokens = cases[test].kv - cases[test].first > TILE
        ? TILE : cases[test].kv - cases[test].first;
    const akv_attention_problem_t problem = {
        .query = &query[0][0], .key = &key[0][0], .value = &value[0][0],
        .mask = mask, .output = &output[0][0],
        .q_row_stride_bytes = sizeof(query[0]),
        .k_token_stride_bytes = sizeof(key[0]),
        .v_token_stride_bytes = sizeof(value[0]),
        .output_row_stride_bytes = sizeof(output[0]),
        .q_rows = rows, .head_dim = DIM, .kv_length = cases[test].kv,
        .scale = 0.0625f,
    };
    akv_attention_plan_t plan;
    if (akv_attention_plan_create_v2(&device, &problem, &plan) != AKV_STATUS_OK)
      return 2;
    __asm__ volatile("csrw frm, %0" : : "r"((uintptr_t)cases[test].rounding) : "memory");
    memset(scores, 0xa5, sizeof(scores));
    memset(reference_scores, 0xa5, sizeof(reference_scores));
    fill(&plan.descriptor, cases[test].first);
    clear_flags();
    akv_v2_compute_scores_f16_d256_generic(&query[0][0], &scores[0][0],
                                         tokens, sizeof(query[0]), rows);
    const unsigned score_flags = flags();
    clear_flags();
    akv_d256_scores_reference(&query[0][0], &reference_scores[0][0],
                             tokens, sizeof(query[0]), rows);
    unsigned errors = memcmp(scores, reference_scores, sizeof(scores)) != 0;
    errors += score_flags != flags();
    if (device.capabilities.token_axis_column_panel4) {
      memset(scores, 0xa5, sizeof(scores));
      clear_flags();
      akv_v2_compute_scores_f16_d256_panel4(&query[0][0], &scores[0][0],
                                          tokens, sizeof(query[0]), rows);
      errors += memcmp(scores, reference_scores, sizeof(scores)) != 0;
      errors += score_flags != flags();
    }

    memcpy(accum, initial_accum, sizeof(accum));
    memcpy(reference_accum, initial_accum, sizeof(accum));
    fill(&plan.value_descriptor, cases[test].first);
    clear_flags();
    akv_v2_update_outputs_f16_d256_generic(&weights[0][0], &accum[0][0],
                                          old_scale, tokens, rows);
    const unsigned output_flags = flags();
    clear_flags();
    akv_d256_outputs_reference(&weights[0][0], &reference_accum[0][0],
                              old_scale, tokens, rows);
    errors += memcmp(accum, reference_accum, sizeof(accum)) != 0;
    errors += output_flags != flags();
    memcpy(accum, initial_accum, sizeof(accum));
    memcpy(reference_accum, initial_accum, sizeof(accum));
    clear_flags();
    akv_v2_update_outputs_f16_d256_online(
        &online_weights[0][0], &accum[0][0], &token_scale[0][0], tokens, rows);
    const unsigned online_flags = flags();
    clear_flags();
    online_reference(rows, tokens, cases[test].first);
    errors += memcmp(accum, reference_accum, sizeof(accum)) != 0;
    errors += online_flags != flags();
    __asm__ volatile(".insn r 0x5b,5,0,x0,x0,x0\ncsrw frm, zero" : : : "memory");
    printf("AKV_D256_REUSE case=%u rows=%u kv=%u first=%u rounding=%u errors=%u\n",
           test, rows, cases[test].kv, cases[test].first, cases[test].rounding, errors);
    if (errors) return 3;
  }
  printf("AKV D256 reuse smoke: PASS cases=8 bit_exact=1\n");
  printf("AKV D256 online PV: PASS cases=8 bit_exact=1\n");
  return 0;
}
