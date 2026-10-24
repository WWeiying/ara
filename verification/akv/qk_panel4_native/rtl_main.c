#include "akv/akv.h"
#include "printf.h"
#include "rtl_data.h"
#include <stdint.h>
#include <string.h>

extern void rtl_akv_full(const akv_descriptor_t *);
extern void rtl_akv_release(void);
extern void akv_v2_compute_scores_f16_d128_gqa6(const uint16_t *, float *, uint32_t, size_t);
extern void akv_v2_compute_scores_f16_d128_gqa6_panel4(const uint16_t *, float *, uint32_t, size_t);
extern const unsigned char rtl_q[], rtl_k[], rtl_v[], rtl_golden[];

typedef struct __attribute__((aligned(64))) {
  unsigned char before[64], bytes[16384], after[64];
} kv_buffer;
static kv_buffer key, value;
static struct __attribute__((aligned(64))) {
  unsigned char before[64], bytes[6 * 320], after[64];
} query;
static struct __attribute__((aligned(64))) {
  unsigned char before[64];
  float values[6 * 64];
  unsigned char after[64];
} score;
static unsigned char query_expected[6 * 320];
static uint32_t baseline[6 * 64];
static float unused_output[6 * 128] __attribute__((aligned(64)));
static uint16_t mask[64] __attribute__((aligned(64)));
static akv_attention_plan_t plan __attribute__((aligned(64)));

static unsigned guard(const unsigned char *p, unsigned n) {
  unsigned errors = 0;
  for (unsigned i = 0; i < n; ++i) errors += p[i] != 0xa5;
  return errors;
}

int main(void) {
  akv_device_t device;
  const akv_status_t status = akv_device_query(akv_native_info, NULL, &device);
  if (status != AKV_STATUS_OK || !device.capabilities.valid ||
      !device.capabilities.f16_payload || !device.capabilities.head_dim_128 ||
      device.capabilities.max_q_rows < 6 || !device.capabilities.token_axis_valid ||
      !device.capabilities.token_axis_tail || !device.capabilities.token_axis_column_panel4) {
    printf("RTL_QK_FAIL reason=capability status=%u\n", (unsigned)status);
    return 1;
  }
  printf("RTL_QK_CAP native=1 panel4=1 pairs=8\n");
  unsigned outputs = 0, tails = 0;
  for (unsigned id = 0; id < 8; ++id) {
    const unsigned vl = rtl_cases[id].vl, stride = rtl_cases[id].stride;
    const unsigned head = rtl_cases[id].head, tile = rtl_cases[id].tile;
    const unsigned offset = (head * 256 + tile) * 256;
    memset(&query, 0xa5, sizeof(query));
    memset(&key, 0xa5, sizeof(key));
    memset(&value, 0xa5, sizeof(value));
    for (unsigned row = 0; row < 6; ++row)
      memcpy(query.bytes + row * stride, rtl_q + (head * 6 + row) * 256, 256);
    memcpy(query_expected, query.bytes, sizeof(query_expected));
    memcpy(key.bytes, rtl_k + offset, sizeof(key.bytes));
    memcpy(value.bytes, rtl_v + offset, sizeof(value.bytes));
    memset(mask, 0, sizeof(mask));
    const akv_attention_problem_t problem = {
      .query = (const uint16_t *)(const void *)query.bytes,
      .key = (const uint16_t *)(const void *)key.bytes,
      .value = (const uint16_t *)(const void *)value.bytes,
      .mask = mask, .output = unused_output,
      .q_row_stride_bytes = stride, .k_token_stride_bytes = 256,
      .v_token_stride_bytes = 256, .output_row_stride_bytes = 512,
      .q_rows = 6, .head_dim = 128, .kv_length = 64, .scale = 1.0f,
    };
    if (akv_attention_plan_create_v2(&device, &problem, &plan) != AKV_STATUS_OK) {
      printf("RTL_QK_FAIL reason=plan case=%u\n", id);
      return 1;
    }
    for (unsigned mode = 0; mode < 2; ++mode) {
      memset(&score, 0xa5, sizeof(score));
      printf("RTL_QK_BEGIN case=%u mode=%u kvhead=%u tile=%u vl=%u stride=%u\n",
             id, mode, head, tile, vl, stride);
      __asm__ volatile("csrwi fcsr, 0; csrwi vcsr, 5" ::: "memory");
      rtl_akv_full(&plan.descriptor);
      if (mode)
        akv_v2_compute_scores_f16_d128_gqa6_panel4(problem.query, score.values, vl, stride);
      else
        akv_v2_compute_scores_f16_d128_gqa6(problem.query, score.values, vl, stride);
      uintptr_t drain, fcsr, vcsr;
      __asm__ volatile("vmv.x.s %0, v12\nfence rw, rw\nfrcsr %1\ncsrr %2, vcsr"
                       : "=&r"(drain), "=&r"(fcsr), "=&r"(vcsr) : : "memory");
      (void)drain;
      rtl_akv_release();
      unsigned errors = fcsr != rtl_cases[id].fcsr || vcsr != 5;
      errors += guard(query.before, 64) + guard(query.after, 64);
      errors += guard(key.before, 64) + guard(key.after, 64);
      errors += guard(value.before, 64) + guard(value.after, 64);
      errors += guard(score.before, 64) + guard(score.after, 64);
      errors += memcmp(query.bytes, query_expected, sizeof(query_expected)) != 0;
      errors += memcmp(key.bytes, rtl_k + offset, sizeof(key.bytes)) != 0;
      errors += memcmp(value.bytes, rtl_v + offset, sizeof(value.bytes)) != 0;
      const unsigned char *expected = rtl_golden + id * 6 * 64 * 4;
      /* Includes every inactive row tail, not just active numerical outputs. */
      errors += memcmp(score.values, expected, sizeof(score.values)) != 0;
      if (!mode) memcpy(baseline, score.values, sizeof(baseline));
      else errors += memcmp(baseline, score.values, sizeof(baseline)) != 0;
      for (unsigned row = 0; row < 6; ++row) {
        printf("RTL_QK_ROW case=%u mode=%u row=%u count=%u bits=", id, mode, row, vl);
        for (unsigned t = 0; t < vl; ++t) {
          uint32_t bits;
          memcpy(&bits, &score.values[row * 64 + t], 4);
          printf("%08x", bits);
        }
        printf("\n");
      }
      printf("RTL_QK_END case=%u mode=%u outputs=%u tailwords=%u guardbytes=512 inputbytes=34688 fcsr=%lu vcsr=%lu errors=%u\n",
             id, mode, 6 * vl, 6 * (64 - vl), (unsigned long)fcsr, (unsigned long)vcsr, errors);
      if (errors) return 1;
      outputs += 6 * vl;
      tails += 6 * (64 - vl);
    }
  }
  printf("RTL_QK_SUITE_PASS pairs=8 runs=16 outputs=%u tailwords=%u\n", outputs, tails);
  return 0;
}
