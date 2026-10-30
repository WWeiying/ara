#define main captured_operator_main
#include "../../apps/llama_q4km_operator/main.c"
#undef main
#include <string.h>

static unsigned panel4_mode;
static uint8_t baseline_output[1536*sizeof(float)] __attribute__((aligned(64)));
extern uint8_t qk_panel4_guard_before[],qk_panel4_guard_after[];

char *getenv(const char *name) {
  if (strcmp(name,"AKV_QK_PANEL4")==0) return panel4_mode ? "1":"0";
  return NULL;
}

int main(void) {
  const case_config_t *cfg=&llama_case_config;
  if (!operator_config_is_valid(cfg) || !attention_shape_is_supported(cfg) ||
      cfg->kind!=CASE_ATTENTION || cfg->flags!=CASE_FLAG_ATTENTION_AKV_V2 ||
      cfg->args[0]!=128 || cfg->args[1]!=1 || cfg->args[2]!=12 || cfg->args[4]!=2 ||
      akv_device_query(akv_native_info,NULL,&attention_akv_device)!=AKV_STATUS_OK ||
      !attention_akv_device.capabilities.token_axis_column_panel4)
    return 1;
  for (unsigned trial=0;trial<4;trial++) {
    panel4_mode=trial==1 || trial==2;
    memset(attention_output,0xa5,sizeof(baseline_output));
    memset(qk_panel4_guard_before,0xa5,64);memset(qk_panel4_guard_after,0xa5,64);
    printf("AKV_QK_TRIAL_BEGIN trial=%u panel4=%u\n",trial,panel4_mode);
    asm volatile("csrwi fcsr, 0; csrwi vcsr, 5":::"memory");
    const uint64_t start=read_cycle();
    const int native=run_attention_akv_v2(cfg);
    asm volatile("vsetivli zero, 0, e32, m1, ta, ma":::"memory");
    const uint64_t cycles=read_cycle()-start;
    uint64_t flags,vcsr;
    asm volatile("frcsr %0; csrr %1, vcsr":"=r"(flags),"=r"(vcsr)::"memory");
    int errors=check_attention(cfg);
    const uint8_t *bytes=(const uint8_t *)(const void *)attention_output;
    if (trial==0) memcpy(baseline_output,bytes,sizeof(baseline_output));
    else errors+=memcmp(baseline_output,bytes,sizeof(baseline_output))!=0;
    for (unsigned i=0;i<64;i++)
      errors+=qk_panel4_guard_before[i]!=0xa5 || qk_panel4_guard_after[i]!=0xa5;
    uint64_t checksum=UINT64_C(14695981039346656037);
    for (unsigned i=0;i<sizeof(baseline_output);i++)
      checksum=(checksum^bytes[i])*UINT64_C(1099511628211);
    printf("AKV_QK_ATTENTION trial=%u panel4=%u native=%d kv=128 outputs=1536 cycles=%lu fcsr=%lu vcsr=%lu checksum=%016lx errors=%d\n",
           trial,panel4_mode,native,(unsigned long)cycles,(unsigned long)flags,
           (unsigned long)vcsr,(unsigned long)checksum,errors);
    if (errors || !native || vcsr!=5) return 1;
  }
  printf("AKV_QK_ABBA_PASS trials=4 outputs_per_trial=1536 bytewise_equal=1 guards=1\n");
  return 0;
}
