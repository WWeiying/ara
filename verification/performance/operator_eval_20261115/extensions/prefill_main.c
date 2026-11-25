#include "runtime.h"
/* Disable inherited phase instrumentation, not arithmetic or loop tiling. */
#undef HW_CNT_PHASE
#define HW_CNT_PHASE(phase) do { (void)(phase); } while (0)
#define main unused_original_operator_main
#include "apps/llama_q4km_operator/main.c"
#undef main
#include "fixture.h"
#include <string.h>

extern const unsigned char fixture_begin[], fixture_end[];
extern unsigned char output_before[], output_after[];
static float saved[2][EXT_OUTPUTS];
static uintptr_t saved_fcsr[2];
static unsigned seen[2];

/* Explicit experimental PV opt-in; the default production policy is unchanged. */
char *getenv(const char *name) {
  return strcmp(name, "AKV_PREFILL_PAIR_PV") == 0 ? "1" : NULL;
}

static uint64_t input_hash(void) {
  uint64_t result = UINT64_C(14695981039346656037);
  for (const unsigned char *p = fixture_begin; p < fixture_end; ++p)
    result = (result ^ *p) * UINT64_C(1099511628211);
  return result;
}

__attribute__((noinline, noclone)) int extensions_full_prefill(unsigned mode) {
  return mode ? run_attention_akv_v2_prefill(&llama_case_config)
              : run_attention_q64_rvv(&llama_case_config);
}

int main(void) {
  if (akv_device_query(akv_native_info, NULL, &attention_akv_device) != AKV_STATUS_OK)
    return 1;
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
  if (vlenb != 128 || !attention_akv_device.capabilities.token_axis_column_panel4)
    return 1;
  const uint64_t original_hash = input_hash();
  printf("EXT_PREFILL_CAP queries=%u first=%u heads=2 kvheads=1 d=128 capacity=256 trials=4 pair_pv=1\n",
         EXT_QUERIES, EXT_FIRST);
  const unsigned order[] = {0, 1, 1, 0};
  for (unsigned trial = 0; trial < 4; ++trial) {
    const unsigned mode = order[trial];
    memset(attention_output, 0xa5, EXT_OUTPUTS * sizeof(float));
    memset(output_before, 0xa5, 64);
    memset(output_after, 0xa5, 64);
    memset(&attention_prefill_workspace, 0, sizeof(attention_prefill_workspace));
    printf("EXT_PREFILL_BEGIN trial=%u mode=%u\n", trial, mode);
    __asm__ volatile("vsetivli zero,1,e32,m1,ta,ma\nvmv.v.i v8,0\ncsrwi fcsr,0\ncsrwi vcsr,5" ::: "memory", "v8");
    uintptr_t start, end, fc, vc, vs;
    __asm__ volatile("csrr zero,cycle" ::: "memory");
    __asm__ volatile("rdcycle %0" : "=r"(start) : : "memory");
    const int ok = extensions_full_prefill(mode);
    /* Same final dependency/memory drain as the checked native Prefill harness. */
    __asm__ volatile("vmv.x.s zero,v8\nfence rw,rw\nrdcycle %0" : "=r"(end) : : "memory");
    __asm__ volatile("csrr zero,cycle" ::: "memory");
    __asm__ volatile("frcsr %0\ncsrr %1,vcsr\ncsrr %2,vstart" : "=r"(fc), "=r"(vc), "=r"(vs));
    unsigned errors = !ok || end <= start || fc > 31 || vc != 5 || vs;
    errors += input_hash() != original_hash;
    for (unsigned i = 0; i < 64; ++i)
      errors += output_before[i] != 0xa5 || output_after[i] != 0xa5;
    const float *gold = (const float *)llama_golden_start;
    for (unsigned i = 0; i < EXT_OUTPUTS; ++i) {
      const float y = attention_output[i];
      errors += !isfinite(y) || !isfinite(gold[i]) ||
                fabsf(y - gold[i]) > .004f + .002f * fabsf(gold[i]);
    }
    if (seen[mode])
      errors += memcmp(saved[mode], attention_output, sizeof(saved[mode])) != 0 || saved_fcsr[mode] != fc;
    else {
      memcpy(saved[mode], attention_output, sizeof(saved[mode]));
      saved_fcsr[mode] = fc;
      seen[mode] = 1;
    }
    printf("EXT_PREFILL_RESULT trial=%u mode=%u cycles=%lu fcsr=%lu vcsr=%lu vstart=%lu guards=128 inputs=1 errors=%u hex=",
           trial, mode, (unsigned long)(end-start), (unsigned long)fc,
           (unsigned long)vc, (unsigned long)vs, errors);
    for (unsigned i = 0; i < EXT_OUTPUTS; ++i) {
      uint32_t word;
      memcpy(&word, attention_output + i, sizeof(word));
      printf("%08x", word);
    }
    printf("\n");
    if (errors) return 1;
  }
  printf("EXT_PREFILL_SUITE_PASS\n");
  return 0;
}
