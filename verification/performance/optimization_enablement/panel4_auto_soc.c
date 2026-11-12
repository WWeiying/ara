#include "../../software/akv/include/akv/akv.h"
#define akv_attention_execute_v2_native(p, w) \
    akv_attention_execute_v2_native_auto(&attention_akv_device, (p), (w))
#define main captured_operator_main
#include "main.c"
#undef main
#undef akv_attention_execute_v2_native
#include <string.h>

static unsigned trial;
static uint8_t baseline_output[1536*sizeof(float)] __attribute__((aligned(64)));
extern uint8_t qk_panel4_guard_before[], qk_panel4_guard_after[];

char *getenv(const char *name) {
  if (strcmp(name, "AKV_QK_PANEL4") == 0)
    return trial == 0 || trial == 3 ? "0" : NULL;
  return NULL;
}

int main(void) {
  const case_config_t *cfg = &llama_case_config;
  if (!operator_config_is_valid(cfg) || !attention_shape_is_supported(cfg) ||
      cfg->kind != CASE_ATTENTION || cfg->flags != CASE_FLAG_ATTENTION_AKV_V2 ||
      cfg->args[0] != 128 || cfg->args[1] != 1 || cfg->args[2] != 12 || cfg->args[4] != 2 ||
      akv_device_query(akv_native_info, NULL, &attention_akv_device) != AKV_STATUS_OK ||
      !attention_akv_device.capabilities.token_axis_column_panel4)
    return 1;
  const akv_device_t admitted = attention_akv_device;
  uint64_t baseline_fcsr = 0, baseline_vcsr = 0;
  for (trial = 0; trial < 5; ++trial) {
    const unsigned selected = trial == 1 || trial == 2;
    const char *request = trial == 4 ? "badcap" : selected ? "auto" : "off";
    attention_akv_device = admitted;
    if (trial == 4)
      attention_akv_device.capabilities.token_axis_column_panel4 = 0;
    memset(attention_output, 0xa5, sizeof(baseline_output));
    memset(qk_panel4_guard_before, 0xa5, 64);
    memset(qk_panel4_guard_after, 0xa5, 64);
    printf("PANEL4_TRIAL_BEGIN trial=%u selected=%u request=%s\n", trial, selected, request);
    asm volatile("csrwi fcsr, 0; csrwi vcsr, 5" ::: "memory");
    const uint64_t start = read_cycle();
    const int native = run_attention_akv_v2(cfg);
    asm volatile("vsetivli zero, 0, e32, m1, ta, ma" ::: "memory");
    const uint64_t cycles = read_cycle()-start;
    uint64_t fcsr, vcsr;
    asm volatile("frcsr %0; csrr %1, vcsr" : "=r"(fcsr), "=r"(vcsr) :: "memory");
    int errors = check_attention(cfg);
    const uint8_t *bytes = (const uint8_t *)(const void *)attention_output;
    if (trial == 0) {
      memcpy(baseline_output, bytes, sizeof(baseline_output));
      baseline_fcsr = fcsr; baseline_vcsr = vcsr;
    } else {
      errors += memcmp(baseline_output, bytes, sizeof(baseline_output)) != 0;
      errors += fcsr != baseline_fcsr || vcsr != baseline_vcsr;
    }
    for (unsigned i = 0; i < 64; ++i)
      errors += qk_panel4_guard_before[i] != 0xa5 || qk_panel4_guard_after[i] != 0xa5;
    uint64_t checksum = UINT64_C(14695981039346656037);
    for (unsigned i = 0; i < sizeof(baseline_output); ++i)
      checksum = (checksum^bytes[i])*UINT64_C(1099511628211);
    printf("PANEL4_ATTENTION trial=%u selected=%u request=%s native=%d kv=128 outputs=1536 cycles=%lu fcsr=%lu vcsr=%lu checksum=%016lx errors=%d\n",
        trial, selected, request, native, (unsigned long)cycles, (unsigned long)fcsr,
        (unsigned long)vcsr, (unsigned long)checksum, errors);
    if (errors || !native || vcsr != 5 || fcsr != 3) return 1;
  }
  printf("PANEL4_AUTO_ABBA_PASS trials=5 outputs_per_trial=1536 bytewise_equal=1 csr_equal=1 guards=1 badcap_fallback=1\n");
  return 0;
}
