#include "akv/akv.h"
#include "akv/akv_decode.h"
#include "printf.h"
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "fixture.h"

extern const unsigned char data_begin[],data_end[],data_guard_before[],data_guard_after[];
void d256_memory_reset(void);
int d256_memory_guards(void);
akv_status_t d256_memory_group(const akv_attention_plan_t *,akv_attention_v2_workspace_t *);
static struct __attribute__((aligned(64))) {
  unsigned char before[64];akv_attention_v2_workspace_t value;unsigned char after[64];
} workspace;
static struct __attribute__((aligned(64))) {
  unsigned char before[64];uint16_t value[4][256];unsigned char after[64];
} query;
static struct __attribute__((aligned(64))) {
  unsigned char before[64];float value[4][256];unsigned char after[64];
} output;
static struct {
  uint64_t begin,end,groups,initial_fcsr,initial_vcsr,initial_vstart,fcsr,vcsr,vstart;
  uint64_t errors,model_errors,hash,query_hash,plan_hash,guard_hash;
  unsigned status,segments,logical_dim,physical_dim,offset,count,rows,tokens;
  uint64_t q,k,kh,v,vh,qh,qstride,kstride,vstride;
  uint32_t diagnostic[64];
} results[2];
char *getenv(const char *name) { (void)name;return NULL; }
static uint64_t hash(uint64_t h,const void *p,size_t n) {
  const volatile unsigned char *s=p;
  for (size_t i=0;i<n;++i) h=(h^s[i])*UINT64_C(1099511628211);
  return h;
}
static int guard(const void *p,size_t n) {
  const unsigned char *s=p;for (size_t i=0;i<n;++i) if (s[i]!=0xa5) return 1;return 0;
}
static uint64_t guards(void) {
  int error=guard(workspace.before,64)+guard(workspace.after,64)+guard(query.before,64)+
      guard(query.after,64)+guard(output.before,64)+guard(output.after,64)+
      guard(data_guard_before,64)+guard(data_guard_after,64);
  for (unsigned h=0;h<8;++h) {
    if (h>=4) error+=guard(workspace.value.accumulator[h],512)+guard(workspace.value.score[h],256)+
        guard(&workspace.value.maximum[h],4)+guard(&workspace.value.sum[h],4)+guard(&workspace.value.old_scale[h],4);
    else error+=guard(&workspace.value.score[h][17],47*4);
  }
  const size_t tail=offsetof(akv_attention_v2_workspace_t,old_scale)+sizeof(workspace.value.old_scale);
  error+=guard((const unsigned char *)&workspace.value+tail,sizeof(workspace.value)-tail);
  return error;
}
static void drain(void) {
  uintptr_t x;__asm__ volatile("vmv.x.s %0,v0\nfence rw,rw":"=r"(x)::"memory");
}
static uint64_t cycle(void) {uint64_t x;__asm__ volatile("rdcycle %0":"=r"(x)::"memory");return x;}
static void csrs(uint64_t *f,uint64_t *v,uint64_t *s) {
  __asm__ volatile("frcsr %0\ncsrr %1,vcsr\ncsrr %2,vstart":"=r"(*f),"=r"(*v),"=r"(*s)::"memory");
}
typedef struct {const akv_device_t *device;unsigned trial;} context_t;
static akv_status_t group(void *opaque,const akv_attention_plan_t *p,uint32_t batch,uint32_t first) {
  context_t *c=opaque;const unsigned t=c->trial;
  results[t].segments=p->d_segment_count;results[t].logical_dim=p->logical_head_dim;
  results[t].physical_dim=p->descriptor.head_dim;results[t].offset=p->d_offset;
  results[t].count=p->d_count;results[t].rows=p->descriptor.q_rows;results[t].tokens=p->descriptor.kv_length;
  results[t].q=p->descriptor.q_base;results[t].qh=p->value_descriptor.q_base;
  results[t].k=p->descriptor.k_base;results[t].kh=p->descriptor.v_base;
  results[t].v=p->value_descriptor.k_base;results[t].vh=p->value_descriptor.v_base;
  results[t].qstride=p->descriptor.q_row_stride_bytes;results[t].kstride=p->descriptor.k_token_stride_bytes;
  results[t].vstride=p->value_descriptor.k_token_stride_bytes;
  results[t].plan_hash=hash(UINT64_C(14695981039346656037),p,sizeof(*p));
  if (batch || first || p->d_segment_count!=2 || p->logical_head_dim!=256 ||
      p->descriptor.head_dim!=128 || p->d_offset || p->d_count!=128 ||
      p->descriptor.q_rows!=4 || p->descriptor.kv_length!=17 ||
      p->descriptor.q_base!=(uintptr_t)query.value || p->descriptor.k_base!=(uintptr_t)fixture_key ||
      p->descriptor.v_base!=(uintptr_t)fixture_key+256 || p->value_descriptor.k_base!=(uintptr_t)fixture_value ||
      p->value_descriptor.v_base!=(uintptr_t)fixture_value+256 ||
      p->value_descriptor.q_base!=(uintptr_t)query.value+256) return AKV_STATUS_LAYOUT;
  akv_status_t status=t?akv_attention_execute_v2_native_auto(c->device,p,&workspace.value):
      d256_memory_group(p,&workspace.value);
  if (results[t].plan_hash!=hash(UINT64_C(14695981039346656037),p,sizeof(*p)))return AKV_STATUS_EXECUTION;
  return status;
}
__attribute__((noinline,noclone)) akv_status_t d256_full_call(unsigned t,uint64_t *groups) {
  for (unsigned h=0;h<4;++h) for (unsigned d=0;d<256;++d) {
    uint32_t bits;__asm__ volatile("fcvt.h.s ft0,%1\nfmv.x.h %0,ft0":"=r"(bits):
        "f"(fixture_query[h*256+d]):"ft0");query.value[h][d]=bits;
  }
  akv_device_t device;
  if (akv_device_query(akv_native_info,NULL,&device)!=AKV_STATUS_OK ||
      !device.capabilities.token_axis_d256_segmented || !device.capabilities.token_axis_column_panel4)
    return AKV_STATUS_CAPABILITY;
  const akv_decode_problem_t p={.query=&query.value[0][0],.key=fixture_key,.value=fixture_value,
      .mask=fixture_mask,.output=&output.value[0][0],.query_bytes=sizeof(query.value),
      .key_bytes=131072,.value_bytes=131072,.mask_bytes=512,.output_bytes=sizeof(output.value),
      .q_head_stride=512,.q_batch_stride=2048,.k_token_stride=512,.k_head_stride=131072,
      .k_batch_stride=131072,.v_token_stride=512,.v_head_stride=131072,.v_batch_stride=131072,
      .mask_batch_stride=0,.output_head_stride=1024,.output_batch_stride=4096,.batches=1,
      .query_heads=4,.kv_heads=1,.kv_length=17,.head_dim=256,.scale=D256_SCALE};
  context_t context={.device=&device,.trial=t};
  return akv_decode_execute(&device,&p,group,&context,groups);
}
int main(void) {
  uintptr_t vlenb;__asm__ volatile("csrr %0,vlenb\nvsetivli zero,1,e32,m1,tu,mu\nvmv.v.i v0,0"
      :"=r"(vlenb)::"v0","memory");
  if (vlenb!=128) {printf("D256_REJECT vlenb=%lu\n",vlenb);return 1;}
  uint64_t errors=0;
  for (unsigned t=0;t<2;++t) {
    memset(&workspace,0xa5,sizeof(workspace));memset(&query,0xa5,sizeof(query));
    memset(&output,0xa5,sizeof(output));d256_memory_reset();drain();
    __asm__ volatile("csrwi fcsr,8\ncsrwi vcsr,5\ncsrwi vstart,0":::"memory");
    csrs(&results[t].initial_fcsr,&results[t].initial_vcsr,&results[t].initial_vstart);
    __asm__ volatile("csrr zero,cycle":::"memory");results[t].begin=cycle();
    results[t].status=d256_full_call(t,&results[t].groups);
    drain();results[t].end=cycle();__asm__ volatile("csrr zero,cycle":::"memory");
    csrs(&results[t].fcsr,&results[t].vcsr,&results[t].vstart);
    results[t].guard_hash=guards();results[t].query_hash=hash(UINT64_C(14695981039346656037),query.value,sizeof(query.value));
    results[t].hash=hash(UINT64_C(14695981039346656037),output.value,sizeof(output.value));
    results[t].errors=results[t].status!=AKV_STATUS_OK || results[t].groups!=1 ||
        results[t].initial_fcsr!=8 || results[t].initial_vcsr!=5 || results[t].initial_vstart ||
        results[t].fcsr!=D256_EXPECT_FCSR || results[t].vcsr!=5 || results[t].vstart ||
        results[t].guard_hash || !d256_memory_guards() || results[t].query_hash!=D256_QUERY_HASH ||
        results[t].hash!=D256_OUTPUT_HASH;
    for (unsigned i=0;i<1024;++i) {
      uint32_t bits;const float x=output.value[i/256][i%256];memcpy(&bits,&x,4);
      results[t].errors+=bits!=fixture_exact[i];
      if (i<64)results[t].diagnostic[i]=bits;
      float delta=x-fixture_model[i];if (delta<0)delta=-delta;
      float m=fixture_model[i];if (m<0)m=-m;
      results[t].model_errors+=(bits&0x7f800000)==0x7f800000 || !(delta<=0.004f+0.002f*m);
    }
    results[t].errors+=results[t].model_errors;errors+=results[t].errors;
  }
  const uint64_t bytes=(uintptr_t)data_end-(uintptr_t)data_begin;
  const uint64_t fingerprint=hash(UINT64_C(14695981039346656037),data_begin,bytes);
  errors+=bytes!=D256_DATA_BYTES || fingerprint!=D256_DATA_HASH;
  for (unsigned t=0;t<2;++t) {
    printf("D256_CALL trial=%u begin=%lu end=%lu groups=%lu status=%u initial_fcsr=%lu initial_vcsr=%lu initial_vstart=%lu fcsr=%lu vcsr=%lu vstart=%lu errors=%lu model_errors=%lu hash=%lx query_hash=%lx guards=%lu\n",
        t,results[t].begin,results[t].end,results[t].groups,results[t].status,results[t].initial_fcsr,
        results[t].initial_vcsr,results[t].initial_vstart,results[t].fcsr,results[t].vcsr,results[t].vstart,
        results[t].errors,results[t].model_errors,results[t].hash,results[t].query_hash,results[t].guard_hash);
    printf("D256_PLAN trial=%u segments=%u logical=%u physical=%u offset=%u count=%u rows=%u tokens=%u q=%lx qh=%lx k=%lx kh=%lx v=%lx vh=%lx qs=%lu ks=%lu vs=%lu\n",
        t,results[t].segments,results[t].logical_dim,results[t].physical_dim,results[t].offset,results[t].count,
        results[t].rows,results[t].tokens,results[t].q,results[t].qh,results[t].k,results[t].kh,results[t].v,
        results[t].vh,results[t].qstride,results[t].kstride,results[t].vstride);
    for (unsigned i=0;i<64;++i)printf("D256_OUT trial=%u index=%u bits=%08x\n",t,i,results[t].diagnostic[i]);
  }
  printf("D256_DATA bytes=%lu hash=%lx\n",bytes,fingerprint);
  printf("D256_DONE calls=2 errors=%lu\n",errors);return errors!=0;
}
