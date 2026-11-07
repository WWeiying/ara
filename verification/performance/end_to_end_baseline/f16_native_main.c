#include "akv/akv.h"
#include "printf.h"
#include "f16_phase_probe.h"
#include <math.h>
#include <riscv_vector.h>
#include <stdint.h>
#include <string.h>

extern const float f16_prefill_query[], f16_prefill_golden[];
extern const float f16_decode_query[], f16_decode_golden[];
extern const uint16_t f16_prefill_key[], f16_prefill_value[], f16_prefill_mask[];
extern const uint16_t f16_decode_key[], f16_decode_value[], f16_decode_mask[], f16_decode_query_f16[];
extern akv_status_t f16_phase_execute_v2_native(const akv_attention_plan_t *, akv_attention_v2_workspace_t *);
extern akv_status_t f16_phase_execute_v2_prefill_native(const akv_device_t *,
    const akv_attention_v2_prefill_problem_t *, akv_attention_v2_prefill_workspace_t *);

uint64_t f16_phase_cycles[F16_PHASE_COUNT], f16_phase_calls[F16_PHASE_COUNT];
void f16_phase_reset(void) {
  memset(f16_phase_cycles, 0, sizeof(f16_phase_cycles));
  memset(f16_phase_calls, 0, sizeof(f16_phase_calls));
}

/* Explicitly retain the already reviewed pair implementations in both peers. */
char *getenv(const char *name) {
  return !strcmp(name, "AKV_PAIR_HEADS") || !strcmp(name, "AKV_PREFILL_PAIR_PV") ? "1" : NULL;
}

#define GUARDED(type, name) static struct __attribute__((aligned(64))) { \
  unsigned char before[64]; type data; unsigned char after[64]; } name
typedef float output_buffer[64*2*128];
typedef uint16_t query_buffer[2*128];
GUARDED(output_buffer, output);
GUARDED(query_buffer, query);
GUARDED(akv_attention_v2_workspace_t, decode_workspace);
GUARDED(akv_attention_v2_prefill_workspace_t, prefill_workspace);
GUARDED(akv_attention_plan_t, plan);
static uint32_t baseline[64*2*128];
static uintptr_t baseline_fc;

static uint64_t stamp(void) {
  uintptr_t vc, fc, vs, cycles;
  __asm__ volatile("csrr %0,vcsr;frcsr %1;csrr %2,vstart;fence rw,rw;rdcycle %3"
      : "=r"(vc), "=r"(fc), "=r"(vs), "=r"(cycles) :: "memory");
  return cycles;
}

static unsigned guard(const void *object, size_t size) {
  const unsigned char *p = object;
  unsigned errors = 0;
  for (unsigned i = 0; i < 64; ++i) errors += p[i] != 0xa5 || p[size-64+i] != 0xa5;
  return errors;
}

static uint64_t hash(const void *data, size_t bytes) {
  const unsigned char *p = data;
  uint64_t value = UINT64_C(14695981039346656037);
  for (size_t i = 0; i < bytes; ++i) value = (value ^ p[i])*UINT64_C(1099511628211);
  return value;
}

static void convert_decode_query(void) {
  for (size_t offset = 0; offset < 256;) {
    const size_t vl = __riscv_vsetvl_e32m4(256-offset);
    const vfloat32m4_t x = __riscv_vle32_v_f32m4(f16_decode_query+offset,vl);
    __riscv_vse16_v_f16m2((_Float16 *)query.data+offset,__riscv_vfncvt_f_f_w_f16m2(x,vl),vl);
    offset += vl;
  }
}

int main(void) {
  akv_device_t device;
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
  if (akv_device_query(akv_native_info,NULL,&device) != AKV_STATUS_OK || vlenb != 128 ||
      !device.capabilities.token_axis_enabled || !device.capabilities.token_axis_column_panel4 ||
      !device.capabilities.f16_payload || !device.capabilities.head_dim_128 ||
      device.capabilities.max_q_rows < 2) return 1;
  printf("F16_REAL_SCOPE model=qwen3_1p7b layer=0 d=128 qheads=2 kvheads=1 capacity=256 prefill=64 decode_visible=137 full_ggml=0\n");
  printf("F16_REAL_BINDINGS baseline=original_native candidate=observation_only pair_heads=1 pair_pv=1 scale_bits=1035273459\n");
  const unsigned order[4] = {0,1,1,0};
  for (unsigned phase = 0; phase < 2; ++phase) {
    const unsigned words = phase ? 64*2*128 : 2*128;
    const float *gold = phase ? f16_prefill_golden : f16_decode_golden;
    for (unsigned trial = 0; trial < 4; ++trial) {
      const unsigned probed = order[trial];
      memset(&output,0xa5,sizeof(output)); memset(&query,0xa5,sizeof(query));
      memset(&decode_workspace,0xa5,sizeof(decode_workspace));
      memset(&prefill_workspace,0xa5,sizeof(prefill_workspace)); memset(&plan,0xa5,sizeof(plan));
      memset(&decode_workspace.data,0,sizeof(decode_workspace.data));
      memset(&prefill_workspace.data,0,sizeof(prefill_workspace.data));
      f16_phase_reset();
      printf("F16_REAL_BEGIN phase=%u trial=%u probed=%u\n",phase,trial,probed);
      __asm__ volatile("csrwi fcsr,8;csrwi vcsr,5;csrwi vstart,0" ::: "memory");
      const uint64_t start = stamp();
      const uint64_t preparation_start = start;
      akv_status_t status;
      uint64_t prepared;
      if (!phase) {
        convert_decode_query();
        const akv_attention_problem_t p = {
          .query=query.data,.key=f16_decode_key,.value=f16_decode_value,.mask=f16_decode_mask,
          .output=output.data,.q_row_stride_bytes=256,.k_token_stride_bytes=256,.v_token_stride_bytes=256,
          .output_row_stride_bytes=512,.q_rows=2,.head_dim=128,.kv_length=137,.scale=0x1.6a09e6p-4f};
        status = akv_attention_plan_create_v2(&device,&p,&plan.data);
        prepared = stamp()-preparation_start;
        if (status == AKV_STATUS_OK)
          status = probed ? f16_phase_execute_v2_native(&plan.data,&decode_workspace.data)
                          : akv_attention_execute_v2_native(&plan.data,&decode_workspace.data);
      } else {
        const akv_attention_v2_prefill_problem_t p = {
          .query=f16_prefill_query,.key=f16_prefill_key,.value=f16_prefill_value,.mask=f16_prefill_mask,
          .output=output.data,.query_tokens=64,.query_heads=2,.kv_heads=1,.kv_capacity=256,
          .head_dim=128,.scale=0x1.6a09e6p-4f,.query_token_stride_bytes=512,.query_head_stride_bytes=32768,
          .key_token_stride_bytes=256,.key_head_stride_bytes=65536,
          .value_token_stride_bytes=256,.value_head_stride_bytes=65536,
          .mask_token_stride_bytes=512,.output_token_stride_bytes=1024};
        prepared = stamp()-preparation_start;
        status = probed ? f16_phase_execute_v2_prefill_native(&device,&p,&prefill_workspace.data)
                        : akv_attention_execute_v2_prefill_native(&device,&p,&prefill_workspace.data);
      }
      const uint64_t elapsed = stamp()-start;
      uintptr_t fc,vc,vs;
      __asm__ volatile("frcsr %0;csrr %1,vcsr;csrr %2,vstart" : "=r"(fc),"=r"(vc),"=r"(vs) :: "memory");
      unsigned errors = status != AKV_STATUS_OK || (fc & ~31u) || !(fc & 8) || vc != 5 || vs;
      errors += guard(&output,sizeof(output))+guard(&query,sizeof(query))+
          guard(&decode_workspace,sizeof(decode_workspace))+guard(&prefill_workspace,sizeof(prefill_workspace))+
          guard(&plan,sizeof(plan));
      if (!phase) errors += memcmp(query.data,f16_decode_query_f16,sizeof(query.data)) != 0;
      for (unsigned i = 0; i < words; ++i) {
        uint32_t bits; memcpy(&bits,&output.data[i],4);
        const float x = output.data[i], y = gold[i];
        if (!isfinite(x) || !isfinite(y) || fabsf(x-y) > .004f+.002f*fabsf(y)) ++errors;
        if (!trial) baseline[i] = bits;
        else errors += baseline[i] != bits;
      }
      for (unsigned i = words*4; i < sizeof(output.data); ++i)
        errors += ((const unsigned char *)output.data)[i] != 0xa5;
      if (!trial) baseline_fc = fc;
      else errors += baseline_fc != fc;
      printf("F16_REAL_RESULT phase=%u trial=%u probed=%u cycles=%lu preparation=%lu words=%u fcsr=%lu vcsr=%lu vstart=%lu errors=%u\n",
          phase,trial,probed,(unsigned long)elapsed,(unsigned long)prepared,words,
          (unsigned long)fc,(unsigned long)vc,(unsigned long)vs,errors);
      for (unsigned id = 0; id < F16_PHASE_COUNT; ++id)
        printf("F16_REAL_PHASE phase=%u trial=%u id=%u calls=%lu cycles=%lu\n",phase,trial,id,
            (unsigned long)f16_phase_calls[id],(unsigned long)f16_phase_cycles[id]);
      /* Every output is checked above; per-row fingerprints avoid making UART
         dump time dominate a bounded RTL measurement. No dump is timed. */
      for (unsigned row = 0; row < (phase ? 64u : 1u); ++row)
        printf("F16_REAL_ROW phase=%u trial=%u row=%u hash=%016lx\n",phase,trial,row,
            (unsigned long)hash(output.data+row*256,256*sizeof(float)));
      if (errors) return 1;
    }
  }
  printf("F16_REAL_SUITE_PASS phases=2 trials=8 words=66560\n");
  return 0;
}
