#include "akv/akv.h"
#include "printf.h"
#include "rtl_data.h"
#include <stdint.h>
#include <string.h>

extern void rtl_akv_full(const akv_descriptor_t *);
extern void rtl_akv_release(void);
extern void akv_v2_compute_scores_f16_generic(const uint16_t *, float *, uint32_t,
                                            size_t, uint32_t, uint32_t);
extern void akv_v2_update_outputs_f16_generic(const float *, uint16_t *, const float *,
                                            uint32_t, uint32_t, uint32_t);
extern void akv_experimental_qk_f16_pair_panel4(const uint16_t *, float *, uint32_t,
                                              size_t, uint32_t);
extern void akv_experimental_pv_f16_pair(const float *, uint16_t *, const float *,
                                      uint32_t, uint32_t);
extern const unsigned char rtl_inputs[], rtl_golden[];

#define BUFFER(name, n) static struct __attribute__((aligned(64))) { \
  unsigned char before[64], bytes[n], after[64]; } name
BUFFER(query, 640);
BUFFER(key, 16384);
BUFFER(value, 16384);
BUFFER(coeff, 512);
BUFFER(scales, 64);
BUFFER(score, 512);
BUFFER(accum, 1024);
BUFFER(mask, 128);
BUFFER(unused, 1024);
static const unsigned char poison[1024] = {[0 ... 1023] = 0xa5};
static const unsigned char zeros[1024];
static unsigned char baseline_qk[512], baseline_pv[1024];
static uintptr_t baseline_pv_fcsr;
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
    printf("PAIR_MISMATCH buffer=%s byte=%u got=%02x expected=%02x\n", name, i, a[i], b[i]);
    break;
  }
}

static uint32_t hash(const unsigned char *p, unsigned n) {
  uint32_t h = UINT32_C(2166136261);
  for (unsigned i = 0; i < n; ++i) h = (h ^ p[i]) * UINT32_C(16777619);
  return h;
}

static void inputs(const unsigned char *src) {
  equal("query", query.bytes, src, 640);
  equal("key", key.bytes, src + 640, 16384);
  equal("value", value.bytes, src + 17024, 16384);
  equal("coeff", coeff.bytes, src + 33408, 512);
  equal("scales", scales.bytes, src + 33920, 64);
  equal("mask", mask.bytes, zeros, 128);
  equal("unused-output", unused.bytes, zeros, 1024);
  equal("descriptor", &plan.descriptor, &descriptor_copy, sizeof(descriptor_copy));
#define GUARDS(b) equal(#b "-before", b.before, poison, 64); \
                  equal(#b "-after", b.after, poison, 64)
  GUARDS(query); GUARDS(key); GUARDS(value); GUARDS(coeff); GUARDS(scales);
  GUARDS(score); GUARDS(accum); GUARDS(mask); GUARDS(unused);
#undef GUARDS
}

static void snapshot(uintptr_t *fcsr, uintptr_t *vcsr) {
  uintptr_t drain;
  /* This image's sequencer gates VMVXS on all older work, not a v12 dependency. */
  __asm__ volatile("vmv.x.s %0, v12\nfence rw, rw\nfrcsr %1\ncsrr %2, vcsr"
                   : "=&r"(drain), "=&r"(*fcsr), "=&r"(*vcsr) : : "memory");
  (void)drain;
}

int main(void) {
  akv_device_t device;
  akv_status_t status = akv_device_query(akv_native_info, NULL, &device);
  const akv_capabilities_t *caps = &device.capabilities;
  uintptr_t vlenb;
  __asm__ volatile("csrr %0, vlenb" : "=r"(vlenb));
  if (status != AKV_STATUS_OK || vlenb != 128 || !caps->valid || !caps->enabled ||
      !caps->f16_payload || !caps->head_dim_64 || !caps->head_dim_128 ||
      caps->max_q_rows < 2 || !caps->token_axis_valid || !caps->token_axis_enabled ||
      !caps->token_axis_tail || !caps->token_axis_row_view ||
      !caps->token_axis_d_axis_tail || !caps->token_axis_column_panel4) {
    printf("PAIR_FAIL reason=capability status=%u vlenb=%lu\n", (unsigned)status, (unsigned long)vlenb);
    return 1;
  }
  printf("PAIR_CAP native=1 panel4=1 vlenb=128 pairs=3\n");
  for (unsigned id = 0; id < 3; ++id) {
    const unsigned d = rtl_cases[id].d, t = rtl_cases[id].tokens, stride = rtl_cases[id].stride;
    if ((d != 64 && d != 96 && d != 128) || !t || t > 64 ||
        stride < 2 * d || stride > 320 || (stride & 1) || rtl_cases[id].head > 1) {
      printf("PAIR_FAIL reason=shape case=%u\n", id);
      return 1;
    }
    const unsigned char *src = rtl_inputs + id * 35008;
    for (unsigned mode = 0; mode < 2; ++mode) {
      errors = reported = 0;
#define INIT(b) memset(&b, 0xa5, sizeof(b))
      INIT(query); INIT(key); INIT(value); INIT(coeff); INIT(scales);
      INIT(score); INIT(accum); INIT(mask); INIT(unused);
#undef INIT
      memcpy(query.bytes, src, 640);
      memcpy(key.bytes, src + 640, 16384);
      memcpy(value.bytes, src + 17024, 16384);
      memcpy(coeff.bytes, src + 33408, 512);
      memcpy(scales.bytes, src + 33920, 64);
      memcpy(accum.bytes, src + 33984, 1024);
      memset(mask.bytes, 0, 128);
      memset(unused.bytes, 0, 1024);
      const akv_attention_problem_t problem = {
        .query = (const uint16_t *)(const void *)query.bytes,
        .key = (const uint16_t *)(const void *)key.bytes,
        .value = (const uint16_t *)(const void *)value.bytes,
        .mask = (const uint16_t *)(const void *)mask.bytes,
        .output = (float *)(void *)unused.bytes,
        .q_row_stride_bytes = stride, .k_token_stride_bytes = 2 * d,
        .v_token_stride_bytes = 2 * d, .output_row_stride_bytes = 512,
        .q_rows = 2, .head_dim = d, .kv_length = 64, .scale = 1.0f,
      };
      if (akv_attention_plan_create_v2(&device, &problem, &plan) != AKV_STATUS_OK) {
        printf("PAIR_FAIL reason=plan case=%u\n", id);
        return 1;
      }
      memcpy(&descriptor_copy, &plan.descriptor, sizeof(descriptor_copy));
      printf("PAIR_BEGIN case=%u mode=%u head=%u d=%u tokens=%u stride=%u\n",
             id, mode, rtl_cases[id].head, d, t, stride);
      rtl_akv_full(&plan.descriptor);
      __asm__ volatile("csrwi fcsr, 8; csrwi vcsr, 5" ::: "memory");
      if (mode) akv_experimental_qk_f16_pair_panel4(problem.query, (float *)(void *)score.bytes, t, stride, d);
      else akv_v2_compute_scores_f16_generic(problem.query, (float *)(void *)score.bytes, t, stride, 2, d);
      uintptr_t fc, vc;
      snapshot(&fc, &vc);
      errors += fc != rtl_cases[id].fcsr || vc != 5;
      equal("qk-oracle", score.bytes, rtl_golden + id * 512, 512);
      if (!mode) memcpy(baseline_qk, score.bytes, 512);
      else equal("qk-baseline", score.bytes, baseline_qk, 512);
      equal("qk-accum-untouched", accum.bytes, src + 33984, 1024);
      inputs(src);
      printf("PAIR_QK case=%u mode=%u outputs=%u tailbytes=%u compared=512 hash=%08x fcsr=%lu vcsr=%lu guardbytes=1152 inputbytes=34112 errors=%u\n",
             id, mode, 2 * t, 512 - 8 * t, hash(score.bytes, 512), (unsigned long)fc, (unsigned long)vc, errors);
      if (errors) { rtl_akv_release(); return 1; }
      __asm__ volatile("csrwi fcsr, 8; csrwi vcsr, 5" ::: "memory");
      if (mode) akv_experimental_pv_f16_pair((const float *)(const void *)coeff.bytes,
                    (uint16_t *)(void *)accum.bytes, (const float *)(const void *)scales.bytes, t, d);
      else akv_v2_update_outputs_f16_generic((const float *)(const void *)coeff.bytes,
                    (uint16_t *)(void *)accum.bytes, (const float *)(const void *)scales.bytes, t, 2, d);
      snapshot(&fc, &vc);
      rtl_akv_release();
      errors += (fc & ~31u) != 0 || !(fc & 8) || vc != 5;
      for (unsigned row = 0; row < 2; ++row)
        equal("pv-gap", accum.bytes + row * 512 + 2 * d, poison, 512 - 2 * d);
      if (!mode) {
        memcpy(baseline_pv, accum.bytes, 1024);
        baseline_pv_fcsr = fc;
      } else {
        equal("pv-baseline", accum.bytes, baseline_pv, 1024);
        errors += fc != baseline_pv_fcsr;
      }
      equal("pv-score-untouched", score.bytes, rtl_golden + id * 512, 512);
      inputs(src);
      printf("PAIR_PV case=%u mode=%u outputs=%u gapbytes=%u baseline_bytes=%u hash=%08x fcsr=%lu vcsr=%lu guardbytes=1152 inputbytes=34112 errors=%u\n",
             id, mode, 2 * d, 1024 - 4 * d, mode ? 1024 : 0, hash(accum.bytes, 1024),
             (unsigned long)fc, (unsigned long)vc, errors);
      if (errors) return 1;
      printf("PAIR_END case=%u mode=%u errors=0\n", id, mode);
    }
  }
  printf("PAIR_SUITE_PASS pairs=3 runs=6 qk_outputs=512 pv_outputs=1152 commands=1044\n");
  return 0;
}
