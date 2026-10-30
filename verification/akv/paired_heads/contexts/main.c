/* Same captured app and ordinary RVV kernel, with an isolated comparator entry. */
#define main captured_operator_main
#include "../../../../apps/llama_q4km_operator/main.c"
#undef main
#include <string.h>
#include "context_data.h"

_Static_assert(CONTEXT_KV == 128 || CONTEXT_KV == 256, "Reviewed contexts only");
_Static_assert(CONTEXT_CAPACITY == 256, "Physical KV layout unchanged");

extern akv_status_t akv_experimental_attention_pair_bench(
    const akv_attention_plan_t *, akv_attention_v2_workspace_t *, unsigned, unsigned *);
extern unsigned char context_output_before[], context_output_after[];

static struct __attribute__((aligned(64))) {
  unsigned char before[64];
  _Float16 data[2 * 128];
  unsigned char after[64];
} context_query;
static struct __attribute__((aligned(64))) {
  unsigned char before[64];
  akv_attention_v2_workspace_t data;
  unsigned char after[64];
} context_workspace;
static akv_attention_plan_t context_plan __attribute__((aligned(64)));
static uint32_t saved_bits[3][512];
static uintptr_t saved_fcsr[3];
static unsigned seen[3];

/* Keep a named call boundary without changing the included ordinary RVV body. */
__attribute__((noinline)) void context_ordinary_rvv(const case_config_t *cfg) {
  run_attention_rvv(cfg);
}

__attribute__((noinline)) int context_native(const case_config_t *cfg,
                                             unsigned paired, unsigned *admitted) {
  akv_device_t device;
  if (akv_device_query(akv_native_info, NULL, &device) != AKV_STATUS_OK) return 0;
  const uint16_t *mask = (const uint16_t *)llama_input_d_start;
  if (attention_active_prefix(mask, CONTEXT_CAPACITY) != CONTEXT_KV) return 0;
  *admitted = 0;
  for (unsigned kvhead = 0; kvhead < 2; ++kvhead) {
    for (unsigned head = 0; head < 2; ++head)
      convert_f32_to_f16_rvv(context_query.data + head * 128,
          (const float *)llama_input_a_start + (kvhead * 2 + head) * 128, 128);
    const akv_attention_problem_t problem = {
      .query = (const uint16_t *)context_query.data,
      .key = (const uint16_t *)llama_input_b_start + kvhead * CONTEXT_CAPACITY * 128,
      .value = (const uint16_t *)llama_input_c_start + kvhead * CONTEXT_CAPACITY * 128,
      .mask = mask, .output = attention_output + kvhead * 256,
      .q_row_stride_bytes = 256, .k_token_stride_bytes = 256,
      .v_token_stride_bytes = 256, .output_row_stride_bytes = 512,
      .q_rows = 2, .head_dim = 128, .kv_length = CONTEXT_KV, .scale = cfg->params[2],
    };
    if (akv_attention_plan_create_v2(&device, &problem, &context_plan) != AKV_STATUS_OK) return 0;
    unsigned effective = 0;
    if (akv_experimental_attention_pair_bench(&context_plan, &context_workspace.data,
                                             paired, &effective) != AKV_STATUS_OK) return 0;
    *admitted += effective;
  }
  return 1;
}

static unsigned guard_errors(const unsigned char *p) {
  unsigned errors = 0;
  for (unsigned i = 0; i < 64; ++i) errors += p[i] != 0xa5;
  return errors;
}

int main(void) {
  const case_config_t *cfg = &llama_case_config;
  if (cfg->magic != 0x514b4d4fu || cfg->version != 1 ||
      !operator_config_is_valid(cfg) || !attention_shape_is_supported(cfg) ||
      cfg->kind != CASE_ATTENTION || cfg->flags != CASE_FLAG_ATTENTION_RVV ||
      cfg->args[0] != 128 || cfg->args[1] != 1 || cfg->args[2] != 4 ||
      cfg->args[3] != CONTEXT_CAPACITY || cfg->args[4] != 2 ||
      cfg->params[0] != .004f || cfg->params[1] != .002f ||
      cfg->params[3] != 0.0f || cfg->params[4] != 0.0f ||
      (uintptr_t)context_output_before + 64 != (uintptr_t)llama_attention_output_start ||
      (uintptr_t)llama_attention_output_end != (uintptr_t)context_output_after) {
    printf("CONTEXT_THREEWAY_FAIL reason=config\n");
    return 1;
  }
  static const unsigned order[6] = {0, 1, 2, 2, 1, 0};
  static const char *const names[3] = {"rvv", "generic", "paired"};
  printf("CONTEXT_THREEWAY_SUBSET source=" CONTEXT_SOURCE_NAME " kv=%u capacity=%u qheads=0,1,6,7 kvheads=0,1 outputs=512 derived=1 outputbytes=2048\n", CONTEXT_KV, CONTEXT_CAPACITY);
  for (unsigned trial = 0; trial < 6; ++trial) {
    const unsigned mode = order[trial];
    memset(context_output_before, 0xa5, 64);
    memset(llama_attention_output_start, 0xa5, 2048);
    memset(context_output_after, 0xa5, 64);
    memset(&context_query, 0xa5, sizeof(context_query));
    memset(context_workspace.before, 0xa5, 64);
    memset(context_workspace.after, 0xa5, 64);
    memset(&context_workspace.data, 0, sizeof(context_workspace.data));
    unsigned admitted = 0;
    int executed = 1;
    printf("CONTEXT_THREEWAY_BEGIN trial=%u variant=%s\n", trial, names[mode]);
    __asm__ volatile("csrwi fcsr, 0; csrwi vcsr, 5" ::: "memory");
    const uint64_t start = read_cycle();
    if (mode == 0) context_ordinary_rvv(cfg);
    else executed = context_native(cfg, mode == 2, &admitted);
    uintptr_t drain;
    /* Accepted sequencer gates scalar extract behind all older vector work. */
    __asm__ volatile("vmv.x.s %0, v0\nfence rw, rw" : "=r"(drain) : : "memory");
    (void)drain;
    const uint64_t cycles = read_cycle() - start;
    uintptr_t fcsr, vcsr;
    __asm__ volatile("frcsr %0; csrr %1, vcsr" : "=r"(fcsr), "=r"(vcsr) : : "memory");
    unsigned errors = !executed || !cycles || admitted != (mode == 2 ? 2u : 0u) ||
                      (fcsr & ~31u) != 0 || vcsr != 5;
    errors += guard_errors(context_output_before) + guard_errors(context_output_after);
    errors += guard_errors(context_query.before) + guard_errors(context_query.after);
    errors += guard_errors(context_workspace.before) + guard_errors(context_workspace.after);
    if (seen[mode]) errors += fcsr != saved_fcsr[mode];
    else saved_fcsr[mode] = fcsr;
    if (mode == 2) errors += !seen[1] || fcsr != saved_fcsr[1];
    const float *golden = (const float *)llama_golden_start;
    unsigned first_reported = 0;
    for (unsigned i = 0; i < 512; ++i) {
      uint32_t bits, expected_bits;
      memcpy(&bits, &attention_output[i], 4);
      memcpy(&expected_bits, &golden[i], 4);
      const unsigned tolerance_error = !isfinite(attention_output[i]) || !isfinite(golden[i]) ||
          !close_f32(attention_output[i], golden[i], cfg->params[0], cfg->params[1]);
      const unsigned repeat_error = seen[mode] && bits != saved_bits[mode][i];
      const unsigned pair_error = mode == 2 && bits != saved_bits[1][i];
      errors += tolerance_error + repeat_error + pair_error;
      if ((tolerance_error || repeat_error || pair_error) && !first_reported) {
        printf("CONTEXT_THREEWAY_MISMATCH trial=%u index=%u got=%08x golden=%08x repeat=%u pair=%u tolerance=%u\n",
               trial, i, bits, expected_bits, repeat_error, pair_error, tolerance_error);
        first_reported = 1;
      }
      if (!seen[mode]) saved_bits[mode][i] = bits;
    }
    ++seen[mode];
    uint64_t checksum = UINT64_C(14695981039346656037);
    const unsigned char *bytes = llama_attention_output_start;
    for (unsigned i = 0; i < 2048; ++i)
      checksum = (checksum ^ bytes[i]) * UINT64_C(1099511628211);
    printf("CONTEXT_THREEWAY_END trial=%u variant=%s executed=%d native=%u admitted_groups=%u outputs=512 cycles=%lu fcsr=%lu vcsr=%lu checksum=%016lx guardbytes=384 errors=%u\n",
           trial, names[mode], executed, mode != 0, admitted, (unsigned long)cycles,
           (unsigned long)fcsr, (unsigned long)vcsr, (unsigned long)checksum, errors);
    if (errors) return 1;
  }
  if (seen[0] != 2 || seen[1] != 2 || seen[2] != 2) return 1;
  printf("CONTEXT_THREEWAY_SUITE_PASS trials=6 outputs_per_trial=512 within_variant_exact=1 generic_paired_exact=1 rvv_tolerance_only=1 guards=1 derived_subset=1\n");
  return 0;
}

