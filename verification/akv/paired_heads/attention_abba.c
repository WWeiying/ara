/* Reuse the real app's RVV Q conversion and capture ABI, not a new kernel. */
#define main captured_operator_main
#include "../../../apps/llama_q4km_operator/main.c"
#undef main
#include <string.h>

extern akv_status_t akv_experimental_attention_pair_bench(
    const akv_attention_plan_t *, akv_attention_v2_workspace_t *, unsigned, unsigned *);

static struct __attribute__((aligned(64))) {
  unsigned char before[64];
  _Float16 data[2 * 128];
  unsigned char after[64];
} pair_query;
static struct __attribute__((aligned(64))) {
  unsigned char before[64];
  float data[4 * 128];
  unsigned char after[64];
} pair_output;
static struct __attribute__((aligned(64))) {
  unsigned char before[64];
  akv_attention_v2_workspace_t data;
  unsigned char after[64];
} pair_workspace;
static uint32_t baseline_bits[512];
static akv_attention_plan_t pair_plan __attribute__((aligned(64)));

static unsigned guard_errors(const unsigned char *bytes) {
  unsigned errors = 0;
  for (unsigned i = 0; i < 64; ++i) errors += bytes[i] != 0xa5;
  return errors;
}

static int execute_pair_attention(const case_config_t *cfg, unsigned mode,
                                  unsigned *admitted_groups) {
  akv_device_t device;
  if (akv_device_query(akv_native_info, NULL, &device) != AKV_STATUS_OK) return 0;
  const uint16_t *mask = (const uint16_t *)llama_input_d_start;
  const int active = attention_active_prefix(mask, 256);
  if (active != 128) return 0;
  *admitted_groups = 0;
  for (unsigned kvhead = 0; kvhead < 2; ++kvhead) {
    for (unsigned head = 0; head < 2; ++head)
      convert_f32_to_f16_rvv(pair_query.data + head * 128,
          (const float *)llama_input_a_start + (kvhead * 6 + head) * 128, 128);
    const akv_attention_problem_t problem = {
      .query = (const uint16_t *)pair_query.data,
      .key = (const uint16_t *)llama_input_b_start + kvhead * 256 * 128,
      .value = (const uint16_t *)llama_input_c_start + kvhead * 256 * 128,
      .mask = mask, .output = pair_output.data + kvhead * 256,
      .q_row_stride_bytes = 256, .k_token_stride_bytes = 256,
      .v_token_stride_bytes = 256, .output_row_stride_bytes = 512,
      .q_rows = 2, .head_dim = 128, .kv_length = 128, .scale = cfg->params[2],
    };
    if (akv_attention_plan_create_v2(&device, &problem, &pair_plan) != AKV_STATUS_OK) return 0;
    unsigned effective = 0;
    if (akv_experimental_attention_pair_bench(&pair_plan, &pair_workspace.data,
                                             mode, &effective) != AKV_STATUS_OK) return 0;
    *admitted_groups += effective;
  }
  return 1;
}

int main(void) {
  const case_config_t *cfg = &llama_case_config;
  if (!operator_config_is_valid(cfg) || !attention_shape_is_supported(cfg) ||
      cfg->kind != CASE_ATTENTION || cfg->flags != CASE_FLAG_ATTENTION_AKV_V2 ||
      cfg->args[0] != 128 || cfg->args[1] != 1 || cfg->args[2] != 12 ||
      cfg->args[3] != 256 || cfg->args[4] != 2) return 1;
  uint64_t initial_fcsr = 0;
  printf("AKV_PAIR_SUBSET source=qwen25_kv128 qheads=0,1,6,7 kvheads=0,1 outputs=512 derived=1\n");
  for (unsigned trial = 0; trial < 4; ++trial) {
    const unsigned mode = trial == 1 || trial == 2;
    memset(&pair_query, 0xa5, sizeof(pair_query));
    memset(&pair_output, 0xa5, sizeof(pair_output));
    memset(pair_workspace.before, 0xa5, 64);
    memset(pair_workspace.after, 0xa5, 64);
    memset(&pair_workspace.data, 0, sizeof(pair_workspace.data));
    printf("AKV_PAIR_TRIAL_BEGIN trial=%u paired=%u\n", trial, mode);
    __asm__ volatile("csrwi fcsr, 0; csrwi vcsr, 5" ::: "memory");
    const uint64_t start = read_cycle();
    unsigned admitted = 0;
    const int native = execute_pair_attention(cfg, mode, &admitted);
    uintptr_t drain;
    __asm__ volatile("vmv.x.s %0, v0\nfence rw, rw" : "=r"(drain) : : "memory");
    (void)drain;
    const uint64_t cycles = read_cycle() - start;
    uintptr_t fcsr, vcsr;
    __asm__ volatile("frcsr %0; csrr %1, vcsr" : "=r"(fcsr), "=r"(vcsr) : : "memory");
    if (trial == 0) initial_fcsr = fcsr;
    unsigned errors = !native || admitted != 2 * mode || fcsr != initial_fcsr ||
                      (fcsr & ~31u) != 0 || vcsr != 5;
    errors += guard_errors(pair_query.before) + guard_errors(pair_query.after);
    errors += guard_errors(pair_output.before) + guard_errors(pair_output.after);
    errors += guard_errors(pair_workspace.before) + guard_errors(pair_workspace.after);
    const float *golden = (const float *)llama_golden_start;
    for (unsigned head = 0; head < 4; ++head) {
      const unsigned source_head = head < 2 ? head : head + 4;
      for (unsigned d = 0; d < 128; ++d) {
        const unsigned i = head * 128 + d;
        const float actual = pair_output.data[i], expected = golden[source_head * 128 + d];
        errors += !isfinite(actual) || !isfinite(expected) ||
                  !close_f32(actual, expected, cfg->params[0], cfg->params[1]);
        uint32_t bits;
        memcpy(&bits, &actual, sizeof(bits));
        if (trial == 0) baseline_bits[i] = bits;
        else errors += bits != baseline_bits[i];
      }
    }
    uint64_t checksum = UINT64_C(14695981039346656037);
    const unsigned char *bytes = (const unsigned char *)pair_output.data;
    for (unsigned i = 0; i < sizeof(pair_output.data); ++i)
      checksum = (checksum ^ bytes[i]) * UINT64_C(1099511628211);
    printf("AKV_PAIR_ATTENTION trial=%u paired=%u admitted_groups=%u native=%d kv=128 outputs=512 cycles=%lu fcsr=%lu vcsr=%lu checksum=%016lx guardbytes=384 errors=%u\n",
           trial, mode, admitted, native, (unsigned long)cycles, (unsigned long)fcsr,
           (unsigned long)vcsr, (unsigned long)checksum, errors);
    if (errors) return 1;
  }
  printf("AKV_PAIR_ABBA_PASS trials=4 outputs_per_trial=512 bytewise_equal=1 guards=1 derived_subset=1\n");
  return 0;
}
