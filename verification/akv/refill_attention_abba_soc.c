#define main captured_operator_main
#include "../../apps/llama_q4km_operator/main.c"
#undef main
#include <string.h>

static unsigned evaluation_mode;
extern akv_status_t __real_akv_attention_execute_v2_native(
    const akv_attention_plan_t *, akv_attention_v2_workspace_t *);
extern akv_status_t akv_attention_execute_v2_native_candidate(
    const akv_attention_plan_t *, akv_attention_v2_workspace_t *);

akv_status_t __wrap_akv_attention_execute_v2_native(
    const akv_attention_plan_t *plan, akv_attention_v2_workspace_t *workspace) {
  return evaluation_mode
      ? akv_attention_execute_v2_native_candidate(plan, workspace)
      : __real_akv_attention_execute_v2_native(plan, workspace);
}

int main(void) {
  const case_config_t *cfg = &llama_case_config;
  if (!operator_config_is_valid(cfg) || !attention_shape_is_supported(cfg) ||
      cfg->kind != CASE_ATTENTION || cfg->flags != CASE_FLAG_ATTENTION_AKV_V2 ||
      cfg->args[0] != 128 || cfg->args[1] != 1 || cfg->args[2] != 12 ||
      cfg->args[4] != 2 ||
      akv_device_init_reference(&attention_akv_device) != AKV_STATUS_OK)
    return 1;
  for (unsigned trial = 0; trial < 4; ++trial) {
    evaluation_mode = trial == 1 || trial == 2;
    memset(attention_output, 0xa5, 1536 * sizeof(float));
    printf("AKV_REFILL_TRIAL_BEGIN trial=%u overlap=%u\n", trial, evaluation_mode);
    asm volatile("csrwi fcsr, 0; csrwi vcsr, 5" ::: "memory");
    const uint64_t start = read_cycle();
    const int native = run_attention_akv_v2(cfg);
    asm volatile("vsetivli zero, 0, e32, m1, ta, ma" ::: "memory");
    const uint64_t cycles = read_cycle() - start;
    uint64_t flags, vcsr;
    asm volatile("csrr %0, fcsr; csrr %1, vcsr" : "=r"(flags), "=r"(vcsr)
                 : : "memory");
    const int errors = check_attention(cfg);
    uint64_t checksum = UINT64_C(14695981039346656037);
    const uint8_t *bytes = (const uint8_t *)(const void *)attention_output;
    for (size_t i = 0; i < 1536 * sizeof(float); ++i) {
      checksum ^= bytes[i];
      checksum *= UINT64_C(1099511628211);
    }
    printf("AKV_REFILL_ATTENTION overlap=%u native=%d kv=128 outputs=1536 "
           "cycles=%lu fcsr=%lu vcsr=%lu checksum=%016lx errors=%d\n",
           evaluation_mode, native, (unsigned long)cycles, (unsigned long)flags,
           (unsigned long)vcsr, (unsigned long)checksum, errors);
    if (errors || !native || vcsr != 5) return 1;
  }
  printf("AKV_REFILL_ABBA_PASS trials=4 outputs_per_trial=1536\n");
  return 0;
}
