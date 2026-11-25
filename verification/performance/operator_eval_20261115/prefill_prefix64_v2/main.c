#include "runtime.h"
#undef HW_CNT_PHASE
#define HW_CNT_PHASE(phase) do { (void)(phase); } while (0)
#define main unused_original_operator_main
#include "apps/llama_q4km_operator/main.c"
#undef main
#include "compact_fixture.h"
#include "validate.h"

extern const unsigned char fixture_begin[], fixture_end[];
extern unsigned char output_before[], output_after[];
const uint64_t compact_contract[] __attribute__((used)) = {COMPACT_CONSTANTS};
static float saved[2][COMPACT_OUTPUTS];
static uintptr_t saved_fcsr[2];
static unsigned seen[2];

char *getenv(const char *name) {
  return strcmp(name,"AKV_PREFILL_PAIR_PV") == 0 ? "1" : NULL;
}

static uint64_t full_hash(const void *source, size_t bytes) {
  const unsigned char *p = source;
  uint64_t h = UINT64_C(14695981039346656037);
  for (size_t i = 0; i < bytes; i += 8) {
    uint64_t word;
    memcpy(&word,p+i,8);
    h = (h ^ word)*UINT64_C(1099511628211);
  }
  return h;
}

__attribute__((noinline, noclone)) int compact_full_prefill(unsigned mode) {
  return mode ? run_attention_akv_v2_prefill(&llama_case_config)
              : run_attention_q64_rvv(&llama_case_config);
}

__attribute__((noinline, noclone)) unsigned compact_audit_all(unsigned trial, unsigned mode,
    uintptr_t start, uintptr_t end, uintptr_t fc, uintptr_t vc, uintptr_t vs, int ok) {
  const compact_check_t check = compact_validate_all(attention_output,
      (const float *)llama_golden_start,COMPACT_OUTPUTS);
  const uint64_t inputs = full_hash(fixture_begin,fixture_end-fixture_begin);
  const uint64_t outputs = full_hash(attention_output,COMPACT_OUTPUTS*sizeof(float));
  unsigned guards = 0;
  for (unsigned i = 0; i < 64; ++i)
    guards += (output_before[i] == 0xa5)+(output_after[i] == 0xa5);
  unsigned repeat_errors = 0;
  if (seen[mode])
    repeat_errors = memcmp(saved[mode],attention_output,sizeof(saved[mode])) != 0 || saved_fcsr[mode] != fc;
  else {
    memcpy(saved[mode],attention_output,sizeof(saved[mode]));
    saved_fcsr[mode] = fc;
    seen[mode] = 1;
  }
  const unsigned errors = !ok || start >= end || fc > 31 || vc != 5 || vs ||
      check.checked != COMPACT_OUTPUTS || check.nonfinite || check.tolerance_errors ||
      guards != 128 || inputs != COMPACT_INPUT_HASH || repeat_errors;
  printf("PFC_RESULT trial=%u mode=%u begin=%lu end=%lu checked=%u nonfinite=%u tolerance_errors=%u "
         "fcsr=%lu vcsr=%lu vstart=%lu guards=%u input_bytes=%u input_hash=%016lx "
         "output_hash=%016lx repeat_errors=%u errors=%u hex=",
         trial,mode,(unsigned long)start,(unsigned long)end,check.checked,check.nonfinite,
         check.tolerance_errors,(unsigned long)fc,(unsigned long)vc,(unsigned long)vs,guards,
         COMPACT_INPUT_BYTES,(unsigned long)inputs,(unsigned long)outputs,repeat_errors,errors);
  for (unsigned i = 0; i < 64; ++i) {
    uint32_t word;
    memcpy(&word,attention_output+i,4);
    printf("%08x",word);
  }
  printf("\n");
  return errors;
}

int main(void) {
  __asm__ volatile("" :: "r"(compact_contract) : "memory");
  if (akv_device_query(akv_native_info,NULL,&attention_akv_device) != AKV_STATUS_OK)
    return 1;
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
  if (vlenb != 128 || !attention_akv_device.capabilities.token_axis_column_panel4)
    return 1;
  printf("PFC_CAP first=0 queries=%u d=128 heads=2 kvheads=1 capacity=256 outputs=%u "
         "printed=64 trials=4 pair_pv=1 atol=3b83126f rtol=3b03126f\n",COMPACT_QUERIES,COMPACT_OUTPUTS);
  const unsigned order[] = {0,1,1,0};
  for (unsigned trial = 0; trial < 4; ++trial) {
    const unsigned mode = order[trial];
    memset(attention_output,0xa5,COMPACT_OUTPUTS*sizeof(float));
    memset(output_before,0xa5,64);
    memset(output_after,0xa5,64);
    memset(&attention_prefill_workspace,0,sizeof(attention_prefill_workspace));
    printf("PFC_BEGIN trial=%u mode=%u\n",trial,mode);
    __asm__ volatile("vsetivli zero,1,e32,m1,ta,ma\nvmv.v.i v8,0\ncsrwi fcsr,0\ncsrwi vcsr,5" ::: "memory","v8");
    uintptr_t start,end,fc,vc,vs;
    __asm__ volatile("csrr zero,cycle" ::: "memory");
    __asm__ volatile("rdcycle %0":"=r"(start)::"memory");
    const int ok = compact_full_prefill(mode);
    __asm__ volatile("vmv.x.s zero,v8\nfence rw,rw\nrdcycle %0":"=r"(end)::"memory");
    __asm__ volatile("csrr zero,cycle" ::: "memory");
    __asm__ volatile("frcsr %0\ncsrr %1,vcsr\ncsrr %2,vstart":"=r"(fc),"=r"(vc),"=r"(vs));
    if (compact_audit_all(trial,mode,start,end,fc,vc,vs,ok)) return 1;
  }
  printf("PFC_DONE calls=4 errors=0\n");
  return 0;
}
