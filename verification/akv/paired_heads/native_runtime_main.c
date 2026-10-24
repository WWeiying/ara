#include "akv/akv.h"
#include "printf.h"
#include <stdint.h>
#include <string.h>

extern const float candidate_query_f32[];
extern const uint16_t candidate_key[], candidate_value[];

/* Harness emulates per-call environment values, not backend dispatch state. */
static unsigned requested;
char *getenv(const char *name) {
  if (strcmp(name, "AKV_PAIR_HEADS") == 0)
    return requested ? "1" : "0";
  return NULL;
}

#define BUFFER(name, type, count) static struct __attribute__((aligned(64))) { \
  unsigned char before[64]; type data[count]; unsigned char after[64]; } name
BUFFER(query, uint16_t, 8*160);
BUFFER(mask, uint16_t, 128);
BUFFER(output, uint32_t, 8*128);
BUFFER(workspace, akv_attention_v2_workspace_t, 1);
static uint32_t baseline[8*128];
static uintptr_t baseline_fcsr;
static akv_attention_plan_t plan __attribute__((aligned(64)));
static akv_descriptor_t descriptor_copy;
static const struct { unsigned dim,heads,kv,source_head; float scale; } cases[] = {
  {64,3,1,0,.125f}, {96,3,65,1,.10206207261596575f},
  {128,6,7,0,.08838834764831843f}, {128,2,64,1,.08838834764831843f}
};

static unsigned guards(const unsigned char *data) {
  unsigned errors = 0;
  for (unsigned i = 0; i < 64; ++i) errors += data[i] != 0xa5;
  return errors;
}

static uint64_t hash(const void *data, size_t size) {
  const unsigned char *p = data;
  uint64_t value = UINT64_C(14695981039346656037);
  for (size_t i = 0; i < size; ++i)
    value = (value ^ p[i])*UINT64_C(1099511628211);
  return value;
}

int main(void) {
  akv_device_t device;
  if (akv_device_query(akv_native_info,NULL,&device) != AKV_STATUS_OK)
    return 1;
  printf("NATIVE_PAIR_CAP cases=4 runs=12 production_candidate=1\n");
  for (unsigned c = 0; c < 4; ++c) {
    const unsigned d = cases[c].dim, heads = cases[c].heads, kv = cases[c].kv;
    for (unsigned trial = 0; trial < 3; ++trial) {
      requested = trial == 1;
      memset(&query,0xa5,sizeof(query));
      memset(&mask,0xa5,sizeof(mask));
      memset(&output,0xa5,sizeof(output));
      memset(&workspace,0xa5,sizeof(workspace));
      memset(&workspace.data[0],0,sizeof(workspace.data[0]));
      for (unsigned h = 0; h < heads; ++h)
        for (unsigned i = 0; i < d; ++i) {
          _Float16 value = (_Float16)candidate_query_f32[(cases[c].source_head*6+h)*128+i];
          memcpy(&query.data[h*160+i],&value,2);
        }
      memset(mask.data,0,kv*2);
      const uint64_t before_query = hash(query.data,sizeof(query.data));
      const uint64_t before_mask = hash(mask.data,sizeof(mask.data));
      const akv_attention_problem_t problem = {
        .query=query.data,.key=candidate_key+cases[c].source_head*256*128,
        .value=candidate_value+cases[c].source_head*256*128,.mask=mask.data,
        .output=(float *)(void *)output.data,.q_row_stride_bytes=320,
        .k_token_stride_bytes=256,.v_token_stride_bytes=256,
        .output_row_stride_bytes=512,.q_rows=heads,.head_dim=d,.kv_length=kv,
        .scale=cases[c].scale};
      if (akv_attention_plan_create_v2(&device,&problem,&plan) != AKV_STATUS_OK)
        return 1;
      memcpy(&descriptor_copy,&plan.descriptor,sizeof(descriptor_copy));
      printf("NATIVE_PAIR_BEGIN case=%u trial=%u requested=%u d=%u heads=%u kv=%u\n",
             c,trial,requested,d,heads,kv);
      __asm__ volatile("csrwi fcsr, 0; csrwi vcsr, 5" ::: "memory");
      const akv_status_t status = akv_attention_execute_v2_native(&plan,&workspace.data[0]);
      uintptr_t drain,fc,vc;
      __asm__ volatile("vmv.x.s %0, v12\nfence rw,rw\nfrcsr %1\ncsrr %2,vcsr"
                       : "=&r"(drain),"=&r"(fc),"=&r"(vc) : : "memory");
      (void)drain;
      unsigned errors = status != AKV_STATUS_OK || (fc & ~31u) || vc != 5;
      errors += before_query != hash(query.data,sizeof(query.data));
      errors += before_mask != hash(mask.data,sizeof(mask.data));
      errors += memcmp(&descriptor_copy,&plan.descriptor,sizeof(descriptor_copy)) != 0;
      for (unsigned h = 0; h < 8; ++h)
        for (unsigned i = 0; i < 128; ++i) {
          const uint32_t bits = output.data[h*128+i];
          errors += h < heads && i < d ?
              (bits & UINT32_C(0x7f800000)) == UINT32_C(0x7f800000) :
              bits != UINT32_C(0xa5a5a5a5);
        }
#define GUARDS(name) errors += guards(name.before)+guards(name.after)
      GUARDS(query); GUARDS(mask); GUARDS(output); GUARDS(workspace);
#undef GUARDS
      if (!trial) {
        memcpy(baseline,output.data,sizeof(baseline));
        baseline_fcsr = fc;
      } else {
        errors += memcmp(baseline,output.data,sizeof(baseline)) != 0;
        errors += baseline_fcsr != fc;
      }
      printf("NATIVE_PAIR_RESULT case=%u trial=%u requested=%u outputs=%u compared=4096 hash=%016lx fcsr=%lu vcsr=%lu errors=%u\n",
             c,trial,requested,heads*d,(unsigned long)hash(output.data,sizeof(output.data)),
             (unsigned long)fc,(unsigned long)vc,errors);
      if (errors) return 1;
    }
  }
  printf("NATIVE_PAIR_SUITE_PASS cases=4 runs=12 exact_outputs=1 exact_flags=1 guards=1\n");
  return 0;
}
