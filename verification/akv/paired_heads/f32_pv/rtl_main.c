#include "akv/akv.h"
#include "printf.h"
#include "rtl_data.h"
#include <stdint.h>
#include <string.h>

extern void rtl_akv_full(const akv_descriptor_t *);
extern void rtl_akv_release(void);
extern void akv_v2_update_outputs_f32_generic(const float *, float *, const float *,
                                            uint32_t, uint32_t, uint32_t);
extern void akv_experimental_pv_f32_pair(const float *, float *, const float *, uint32_t, uint32_t);
extern const unsigned char rtl_inputs[], rtl_golden[];

#define BUFFER(name, n) static struct __attribute__((aligned(64))) { \
  unsigned char before[64], bytes[n], after[64]; } name
BUFFER(query, 512);
BUFFER(key, 16384);
BUFFER(value, 16384);
BUFFER(coeff, 512);
BUFFER(scales, 64);
BUFFER(accum, 1024);
BUFFER(mask, 128);
BUFFER(unused, 1024);
static const unsigned char poison[1024] = {[0 ... 1023] = 0xa5};
static const unsigned char zeros[1024];
static unsigned char baseline[1024];
static uintptr_t baseline_fcsr;
static akv_attention_plan_t plan __attribute__((aligned(64)));
static akv_descriptor_t descriptor_copy;
static unsigned errors, reported;

static void equal(const char *name, const void *actual, const void *expected, unsigned n) {
  if (!memcmp(actual, expected, n)) return;
  ++errors;
  if (reported) return;
  reported = 1;
  const unsigned char *a = actual, *b = expected;
  for (unsigned i = 0; i < n; ++i) if (a[i] != b[i]) {
    printf("F32_PV_MISMATCH buffer=%s byte=%u got=%02x expected=%02x\n", name, i, a[i], b[i]);
    break;
  }
}

static uint32_t hash(const unsigned char *p, unsigned n) {
  uint32_t h = UINT32_C(2166136261);
  for (unsigned i = 0; i < n; ++i) h = (h ^ p[i]) * UINT32_C(16777619);
  return h;
}

static void inputs(const unsigned char *src) {
  equal("query", query.bytes, src, 512);
  equal("key", key.bytes, src + 512, 16384);
  equal("value", value.bytes, src + 16896, 16384);
  equal("coeff", coeff.bytes, src + 33280, 512);
  equal("scales", scales.bytes, src + 33792, 64);
  equal("mask", mask.bytes, zeros, 128);
  equal("unused", unused.bytes, zeros, 1024);
  equal("descriptor", &plan.descriptor, &descriptor_copy, sizeof(descriptor_copy));
#define GUARDS(b) equal(#b "-before", b.before, poison, 64); \
                  equal(#b "-after", b.after, poison, 64)
  GUARDS(query); GUARDS(key); GUARDS(value); GUARDS(coeff);
  GUARDS(scales); GUARDS(accum); GUARDS(mask); GUARDS(unused);
#undef GUARDS
}

int main(void) {
  akv_device_t device;
  akv_status_t status = akv_device_query(akv_native_info, NULL, &device);
  const akv_capabilities_t *c = &device.capabilities;
  uintptr_t vlenb;
  __asm__ volatile("csrr %0, vlenb" : "=r"(vlenb));
  if (status != AKV_STATUS_OK || vlenb != 128 || !c->valid || !c->enabled ||
      !c->f16_payload || !c->context_count || c->max_q_rows < 2 ||
      !c->token_axis_valid || !c->token_axis_enabled || !c->token_axis_tail ||
      !c->token_axis_row_view || c->token_axis_tile_tokens != 64 ||
      !c->head_dim_64 || !c->head_dim_128 || !c->token_axis_d_axis_tail) {
    printf("F32_PV_FAIL reason=capability status=%u\n", (unsigned)status);
    return 1;
  }
  printf("F32_PV_CAP native=1 vlenb=128 pairs=3 resident=64\n");
  for (unsigned id = 0; id < 3; ++id) {
    const unsigned d = rtl_cases[id].d, t = rtl_cases[id].tokens;
    if ((d != 64 && d != 96 && d != 128) || !t || t > 64) return 1;
    const unsigned char *src = rtl_inputs + id * 34880;
    for (unsigned mode = 0; mode < 2; ++mode) {
      errors = reported = 0;
#define INIT(b) memset(&b, 0xa5, sizeof(b))
      INIT(query); INIT(key); INIT(value); INIT(coeff);
      INIT(scales); INIT(accum); INIT(mask); INIT(unused);
#undef INIT
      memcpy(query.bytes, src, 512);
      memcpy(key.bytes, src + 512, 16384);
      memcpy(value.bytes, src + 16896, 16384);
      memcpy(coeff.bytes, src + 33280, 512);
      memcpy(scales.bytes, src + 33792, 64);
      memcpy(accum.bytes, src + 33856, 1024);
      memset(mask.bytes, 0, 128);
      memset(unused.bytes, 0, 1024);
      const akv_attention_problem_t problem = {
        .query = (const uint16_t *)(const void *)query.bytes,
        .key = (const uint16_t *)(const void *)key.bytes,
        .value = (const uint16_t *)(const void *)value.bytes,
        .mask = (const uint16_t *)(const void *)mask.bytes,
        .output = (float *)(void *)unused.bytes,
        .q_row_stride_bytes = 2 * d, .k_token_stride_bytes = 2 * d,
        .v_token_stride_bytes = 2 * d, .output_row_stride_bytes = 4 * d,
        .q_rows = 2, .head_dim = d, .kv_length = 64, .scale = 1.0f,
      };
      if (akv_attention_plan_create_v2(&device, &problem, &plan) != AKV_STATUS_OK) return 1;
      memcpy(&descriptor_copy, &plan.descriptor, sizeof(descriptor_copy));
      printf("F32_PV_BEGIN case=%u mode=%u d=%u tokens=%u stride=%u\n", id, mode, d, t, 4 * d);
      rtl_akv_full(&plan.descriptor);
      __asm__ volatile("csrwi fcsr, 8; csrwi vcsr, 5" ::: "memory");
      if (mode) akv_experimental_pv_f32_pair((const float *)(const void *)coeff.bytes,
          (float *)(void *)accum.bytes, (const float *)(const void *)scales.bytes, t, d);
      else akv_v2_update_outputs_f32_generic((const float *)(const void *)coeff.bytes,
          (float *)(void *)accum.bytes, (const float *)(const void *)scales.bytes, t, 2, d);
      uintptr_t drain, fc, vc;
      __asm__ volatile("vmv.x.s %0, v12\nfence rw, rw\nfrcsr %1\ncsrr %2, vcsr"
          : "=&r"(drain), "=&r"(fc), "=&r"(vc) : : "memory");
      (void)drain;
      rtl_akv_release();
      errors += fc != rtl_cases[id].fcsr || vc != 5;
      equal("independent-oracle", accum.bytes, rtl_golden + id * 1024, 1024);
      equal("output-tail", accum.bytes + 8 * d, poison, 1024 - 8 * d);
      if (!mode) {
        memcpy(baseline, accum.bytes, 1024);
        baseline_fcsr = fc;
      } else {
        equal("generic-paired", accum.bytes, baseline, 1024);
        errors += fc != baseline_fcsr;
      }
      inputs(src);
      printf("F32_PV_RESULT case=%u mode=%u outputs=%u tailbytes=%u compared=1024 hash=%08x fcsr=%lu vcsr=%lu guardbytes=1024 inputbytes=35072 errors=%u\n",
          id, mode, 2 * d, 1024 - 8 * d, hash(accum.bytes, 1024), (unsigned long)fc, (unsigned long)vc, errors);
      if (errors) return 1;
    }
  }
  printf("F32_PV_SUITE_PASS pairs=3 runs=6 outputs=1152 commands=396\n");
  return 0;
}
