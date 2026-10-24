#include "qbs/qbs.h"
#include "verification/qbs/qbs_ref.h"
#include "printf.h"
#include <stdint.h>
#include <stddef.h>
#include <string.h>

extern void quantize_row_q8_0(const float *,void *,int64_t);
extern void ggml_vec_dot_q4_0_q8_0(int,float *,size_t,const void *,size_t,const void *,size_t,int);
extern void ggml_vec_dot_q8_0_q8_0(int,float *,size_t,const void *,size_t,const void *,size_t,int);
extern const float quant_query0_f32[],quant_query1_f32[];
extern const unsigned char quant_key0[],quant_key1[];

static struct __attribute__((aligned(64))) {
  unsigned char before[64],data[136],after[64];
} activation;
static struct __attribute__((aligned(64))) {
  unsigned char before[64]; float data[32]; unsigned char after[64];
} output;
static float reference[32] __attribute__((aligned(64)));
static qbs_descriptor_t descriptor __attribute__((aligned(64)));

/* Original reference arithmetic is unmodified. Its one result allocation is
 * supplied by a bounded, non-reentrant fixture instead of a bare-metal heap. */
static float reference_storage[32] __attribute__((aligned(64)));
static unsigned reference_busy,allocator_errors;
void *quant_ref_calloc(size_t count,size_t bytes) {
  if (reference_busy || !count || !bytes || count > sizeof(reference_storage)/bytes) {
    ++allocator_errors;
    return NULL;
  }
  reference_busy = 1;
  memset(reference_storage,0,sizeof(reference_storage));
  return reference_storage;
}
void quant_ref_free(void *data) {
  if (data != reference_storage || !reference_busy) ++allocator_errors;
  reference_busy = 0;
}

static void snapshot(uintptr_t *fc,uintptr_t *vc) {
  uintptr_t drain;
  __asm__ volatile("vmv.x.s %0,v12\nfence rw,rw\nfrcsr %1\ncsrr %2,vcsr"
    : "=&r"(drain),"=&r"(*fc),"=&r"(*vc) : : "memory");
  (void)drain;
}

static uint32_t bits(float value) {
  uint32_t result;
  memcpy(&result,&value,4);
  return result;
}

static unsigned guards(void) {
  unsigned errors = 0;
  for (unsigned i = 0; i < 64; ++i)
    errors += activation.before[i] != 0xa5 || activation.after[i] != 0xa5 ||
              output.before[i] != 0xa5 || output.after[i] != 0xa5;
  for (unsigned i = 1; i < 32; ++i) errors += bits(output.data[i]) != UINT32_C(0xa5a5a5a5);
  return errors;
}

int main(void) {
  qbs_device_t device;
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
  if (vlenb != 128 || qbs_device_query(qbs_native_info,NULL,&device) != QBS_STATUS_OK ||
      !(device.weight_profiles & (1u<<QBS_WEIGHT_PROFILE_Q8_0_WEIGHT)) ||
      !(device.weight_profiles & (1u<<QBS_WEIGHT_PROFILE_Q4_0))) return 1;
  const float *const queries[] = {quant_query0_f32,quant_query1_f32};
  const unsigned char *const keys[] = {quant_key0,quant_key1};
  const unsigned rows[] = {136,72},tokens[] = {0,63,64,127};
  unsigned comparisons = 0,differences[2] = {0,0};
  printf("QUANT_KV_CAP source=actual_ggml_rvv profiles=2 heads=2 tokens=4 d=128 commands=16\n");
  for (unsigned kind = 0; kind < 2; ++kind) {
    for (unsigned head = 0; head < 2; ++head) {
      memset(&activation,0xa5,sizeof(activation));
      __asm__ volatile("csrwi fcsr,0; csrwi vcsr,5" ::: "memory");
      quantize_row_q8_0(queries[kind]+head*6*128,activation.data,128);
      uintptr_t quant_fc,quant_vc;
      snapshot(&quant_fc,&quant_vc);
      if (quant_fc > 31 || quant_vc != 5) return 1;
      printf("QUANT_KV_QUERY kind=%u head=%u bytes=136 fcsr=%lu vcsr=5 hex=",kind,head,(unsigned long)quant_fc);
      for (unsigned b = 0; b < 136; ++b) printf("%02x",activation.data[b]);
      printf("\n");
      for (unsigned index = 0; index < 4; ++index) {
        const unsigned token = tokens[index];
        const unsigned char *weight = keys[kind]+(head*256+token)*rows[kind];
        float rvv;
        __asm__ volatile("csrwi fcsr,0; csrwi vcsr,5" ::: "memory");
        if (!kind) ggml_vec_dot_q8_0_q8_0(128,&rvv,0,weight,0,activation.data,0,1);
        else ggml_vec_dot_q4_0_q8_0(128,&rvv,0,weight,0,activation.data,0,1);
        uintptr_t rvv_fc,rvv_vc;
        snapshot(&rvv_fc,&rvv_vc);
        qbs_descriptor_fields_t fields = {0};
        fields.descriptor_version = QBS_DESCRIPTOR_VERSION;
        fields.weight_profile = kind ? QBS_WEIGHT_PROFILE_Q4_0 : QBS_WEIGHT_PROFILE_Q8_0_WEIGHT;
        fields.activation_profile = QBS_ACTIVATION_PROFILE_Q8_0;
        fields.weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR;
        fields.activation_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR;
        fields.n = 1; fields.k_blocks = 4;
        fields.activation_access = QBS_ACTIVATION_ACCESS_DIRECT;
        descriptor.header = qbs_pack_descriptor_header(&fields);
        descriptor.weight_base = (uintptr_t)weight;
        memset(&output,0xa5,sizeof(output));
        __asm__ volatile("csrwi fcsr,0; csrwi vcsr,5" ::: "memory");
        const qbs_status_t status = qbs_native_execute_command(NULL,&descriptor,1,
            activation.data,output.data,32,1,0);
        uintptr_t hw_fc,hw_vc;
        snapshot(&hw_fc,&hw_vc);
        qbs_ref_result_t result = {0};
        const qbs_ref_status_t ref_status = qbs_ref_execute(&descriptor,1,8,1024,
            (uintptr_t)activation.data,weight,rows[kind],activation.data,136,
            reference,32,NULL,NULL,&result);
        const unsigned errors = status != QBS_STATUS_OK || ref_status != QBS_REF_OK ||
            bits(output.data[0]) != bits(reference[0]) || hw_fc != result.fflags ||
            (bits(rvv) & UINT32_C(0x7f800000)) == UINT32_C(0x7f800000) ||
            (bits(output.data[0]) & UINT32_C(0x7f800000)) == UINT32_C(0x7f800000) ||
            hw_fc > 31 || hw_vc != 5 || rvv_fc > 31 || rvv_vc != 5 || guards() ||
            allocator_errors || reference_busy;
        const unsigned equal = bits(rvv) == bits(output.data[0]) && rvv_fc == hw_fc;
        differences[kind] += !equal;
        printf("QUANT_KV_SCORE kind=%u head=%u token=%u rvv=%08x qbs=%08x ref=%08x rvv_flags=%lu qbs_flags=%lu ref_flags=%u equal=%u errors=%u\n",
            kind,head,token,bits(rvv),bits(output.data[0]),bits(reference[0]),
            (unsigned long)rvv_fc,(unsigned long)hw_fc,result.fflags,equal,errors);
        if (errors) return 1;
        ++comparisons;
      }
    }
  }
  printf("QUANT_KV_SUITE_PASS comparisons=%u q8_differences=%u q4_differences=%u hardware_reference_exact=1 deployment_accepted=0\n",
         comparisons,differences[0],differences[1]);
  return 0;
}
