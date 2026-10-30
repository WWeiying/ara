#include "akv/akv.h"
#include "printf.h"
#include <math.h>
#include <stdint.h>
#include <string.h>

extern const float prefill_query[],prefill_golden[];
extern const uint16_t prefill_key[],prefill_value[],prefill_mask[];
static unsigned requested;
char *getenv(const char *name) {
  return strcmp(name,"AKV_PREFILL_PAIR_PV") == 0 ? (requested ? "1" : "0") : NULL;
}
static struct __attribute__((aligned(64))) {
  unsigned char before[64];
  float data[2304];
  unsigned char after[64];
} output;
static struct __attribute__((aligned(64))) {
  unsigned char before[64];
  akv_attention_v2_prefill_workspace_t data;
  unsigned char after[64];
} workspace;
static unsigned char baseline[9216];
static uintptr_t baseline_fcsr;

static uint64_t hash(const void *data,size_t count) {
  const unsigned char *p = data;
  uint64_t value = UINT64_C(14695981039346656037);
  for (size_t i = 0; i < count; ++i) value = (value ^ p[i])*UINT64_C(1099511628211);
  return value;
}

int main(void) {
  akv_device_t device;
  if (akv_device_query(akv_native_info,NULL,&device) != AKV_STATUS_OK) return 1;
  const akv_attention_v2_prefill_problem_t problem = {
    .query=prefill_query,.key=prefill_key,.value=prefill_value,.mask=prefill_mask,
    .output=output.data,.query_tokens=4,.query_heads=9,.kv_heads=3,.kv_capacity=256,
    .head_dim=64,.scale=.125f,.query_token_stride_bytes=256,.query_head_stride_bytes=1024,
    .key_token_stride_bytes=128,.key_head_stride_bytes=32768,
    .value_token_stride_bytes=128,.value_head_stride_bytes=32768,
    .mask_token_stride_bytes=512,.output_token_stride_bytes=2304};
  printf("PREFILL_PV_SLICE source=smollm2_m64 positions=32-35 heads=9 kvheads=3 d=64 outputs=2304 derived=1\n");
  const unsigned order[4] = {0,1,1,0};
  for (unsigned trial = 0; trial < 4; ++trial) {
    requested = order[trial];
    memset(&output,0xa5,sizeof(output));
    memset(&workspace,0xa5,sizeof(workspace));
    memset(&workspace.data,0,sizeof(workspace.data));
    printf("PREFILL_PV_BEGIN trial=%u paired=%u\n",trial,requested);
    __asm__ volatile("csrwi fcsr,0; csrwi vcsr,5" ::: "memory");
    uintptr_t start,end,drain,fc,vc;
    __asm__ volatile("rdcycle %0" : "=r"(start) : : "memory");
    const akv_status_t status = akv_attention_execute_v2_prefill_native(&device,&problem,&workspace.data);
    __asm__ volatile("vmv.x.s %0,v12\nfence rw,rw\nrdcycle %1\nfrcsr %2\ncsrr %3,vcsr"
      : "=&r"(drain),"=&r"(end),"=&r"(fc),"=&r"(vc) : : "memory");
    (void)drain;
    unsigned errors = status != AKV_STATUS_OK || (fc & ~31u) || vc != 5 || end <= start;
    for (unsigned i = 0; i < 2304; ++i) {
      const float actual = output.data[i],expected = prefill_golden[i];
      if (!isfinite(actual) || !isfinite(expected) ||
          fabsf(actual-expected) > .004f+.002f*fabsf(expected)) {
        if (!errors) printf("PREFILL_PV_MISMATCH trial=%u output=%u\n",trial,i);
        ++errors;
      }
    }
    for (unsigned i = 0; i < 64; ++i)
      errors += output.before[i] != 0xa5 || output.after[i] != 0xa5 ||
                workspace.before[i] != 0xa5 || workspace.after[i] != 0xa5;
    if (!trial) {
      memcpy(baseline,output.data,sizeof(baseline));
      baseline_fcsr = fc;
    } else {
      errors += memcmp(baseline,output.data,sizeof(baseline)) != 0 || baseline_fcsr != fc;
    }
    printf("PREFILL_PV_RESULT trial=%u paired=%u outputs=2304 cycles=%lu fcsr=%lu vcsr=%lu hash=%016lx guards=256 errors=%u\n",
      trial,requested,(unsigned long)(end-start),(unsigned long)fc,(unsigned long)vc,
      (unsigned long)hash(output.data,sizeof(output.data)),errors);
    if (errors) return 1;
  }
  printf("PREFILL_PV_SUITE_PASS trials=4 outputs=2304 generic_pair_exact=1 golden_tolerance=1\n");
  return 0;
}
