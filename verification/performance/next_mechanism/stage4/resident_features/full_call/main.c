#include "akv/akv.h"
#include "akv/akv_decode.h"
#include "resident_attention/features_v2/executor.h"
#include "printf.h"
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "fixture.h"

enum { HEADS=6, STRIDE=128, GUARD=64 };
_Static_assert(sizeof(akv_attention_v2_workspace_t)==6272,"Workspace ABI");
volatile uint32_t resident_pv_rotation_selected=1;
static struct __attribute__((aligned(64))) {
  unsigned char before[GUARD]; akv_attention_v2_workspace_t value; unsigned char after[GUARD];
} workspace;
static struct __attribute__((aligned(64))) {
  unsigned char before[GUARD]; uint16_t value[HEADS][STRIDE]; unsigned char after[GUARD];
} query;
static struct __attribute__((aligned(64))) {
  unsigned char before[GUARD]; float value[HEADS][STRIDE]; unsigned char after[GUARD];
} output;
static struct {
  uint64_t begin,returned,end,initial_fcsr,fcsr,vcsr,vstart,groups,errors,query_hash,guard_hash,guard_bytes;
  struct { uint32_t first,rows; uint64_t q,k,v,out; } group[2];
  uint32_t bits[HEADS*STRIDE];
} results[FEATURE_CALLS];

char *getenv(const char *name) {
  return strcmp(name,"AKV_PAIR_HEADS")==0 ? "1" : NULL;
}
static uint64_t cycles(void) {
  uint64_t value;__asm__ volatile("rdcycle %0":"=r"(value)::"memory");return value;
}
static void drain(void) {
  uintptr_t value;
  __asm__ volatile("vmv.x.s %0,v0\nfence rw,rw":"=r"(value)::"memory");
}
static uint64_t hash(uint64_t value,const volatile void *pointer,size_t n) {
  const volatile unsigned char *p=pointer;
  for(size_t i=0;i<n;++i)value=(value^p[i])*UINT64_C(1099511628211);
  return value;
}
static uint64_t guards(const feature_case_t *c,uint64_t *bytes) {
  uint64_t value=UINT64_C(14695981039346656037);*bytes=0;
#define HASH(p,n) do {size_t size=(n);value=hash(value,p,size);*bytes+=size;} while(0)
  HASH(workspace.before,GUARD);HASH(workspace.after,GUARD);
  HASH(query.before,GUARD);HASH(query.after,GUARD);HASH(output.before,GUARD);HASH(output.after,GUARD);
  for(unsigned h=0;h<HEADS;++h) {
    const unsigned first=h<c->heads?c->d:0;
    HASH(query.value[h]+first,(STRIDE-first)*2);HASH(output.value[h]+first,(STRIDE-first)*4);
  }
  for(unsigned h=0;h<AKV_MAX_Q_ROWS;++h) {
    const unsigned first=h<c->rows?c->d:0;
    HASH(workspace.value.accumulator[h]+first,(AKV_HEAD_DIM_256-first)*2);
    if(h>=c->rows) {
      HASH(workspace.value.score[h],sizeof(workspace.value.score[h]));
      HASH(&workspace.value.maximum[h],4);HASH(&workspace.value.sum[h],4);HASH(&workspace.value.old_scale[h],4);
    }
  }
  const size_t tail=offsetof(akv_attention_v2_workspace_t,old_scale)+sizeof(workspace.value.old_scale);
  HASH((const unsigned char *)&workspace.value+tail,sizeof(workspace.value)-tail);
#undef HASH
  return value;
}
typedef struct {
  const feature_case_t *c;const feature_trial_t *trial;const akv_device_t *device;
  unsigned index,visited,preflight;
} context_t;
static akv_status_t execute_group(void *opaque,const akv_attention_plan_t *plan,
                                  uint32_t batch,uint32_t first_head) {
  context_t *ctx=opaque;const feature_case_t *c=ctx->c;const unsigned group=first_head/c->rows;
  if(batch || first_head!=ctx->visited*c->rows || group>=c->heads/c->rows ||
     plan->descriptor.q_rows!=c->rows || plan->descriptor.head_dim!=c->d ||
     plan->descriptor.q_base!=(uintptr_t)&query.value[first_head][0] ||
     plan->descriptor.k_base!=(uintptr_t)(feature_data+FEATURE_KEY_OFFSET+group*65536) ||
     plan->descriptor.v_base!=(uintptr_t)(feature_data+FEATURE_VALUE_OFFSET+group*65536) ||
     plan->output!=&output.value[first_head][0] || plan->output_row_stride_bytes!=512)
    return AKV_STATUS_LAYOUT;
  const akv_resident_features_v2_options_t options={
    .abi_version=2,.struct_bytes=sizeof(options),.score_policy=1,.row_meaning=1,
    .query_tokens=1,.feature_rows=c->rows,.requested=ctx->trial->requested,
    .validated_available=1,.platform_admitted=1,.whole_call_owned=1,
    .refill_overlap=0,.vlenb=128,.frm=0,.vstart=0};
  ++ctx->visited;
  if(ctx->preflight)return akv_resident_features_v2_contract(plan,&c->features[group],&options);
  results[ctx->index].group[group].first=first_head;results[ctx->index].group[group].rows=c->rows;
  results[ctx->index].group[group].q=plan->descriptor.q_base;
  results[ctx->index].group[group].k=plan->descriptor.k_base;
  results[ctx->index].group[group].v=plan->descriptor.v_base;
  results[ctx->index].group[group].out=(uintptr_t)plan->output;
  return akv_experimental_attention_execute_features_v2_native(
      ctx->device,plan,&workspace.value,&c->features[group],&options,0);
}
__attribute__((noinline,noclone)) akv_status_t feature_full_call(unsigned index,uint64_t *groups) {
  const feature_trial_t *trial=&feature_trials[index];const feature_case_t *c=&feature_cases[trial->index];
  akv_device_t device;
  if(akv_device_query(akv_native_info,NULL,&device)!=AKV_STATUS_OK)return AKV_STATUS_CAPABILITY;
  const unsigned kvheads=c->heads/c->rows;
  const akv_decode_problem_t problem={
    .query=&query.value[0][0],.key=(const uint16_t *)(feature_data+FEATURE_KEY_OFFSET),
    .value=(const uint16_t *)(feature_data+FEATURE_VALUE_OFFSET),
    .mask=(const uint16_t *)(feature_data+c->mask_offset),.output=&output.value[0][0],
    .query_bytes=sizeof(query.value),.key_bytes=kvheads*65536,.value_bytes=kvheads*65536,
    .mask_bytes=512,.output_bytes=sizeof(output.value),.q_head_stride=256,.q_batch_stride=c->heads*256,
    .k_token_stride=256,.k_head_stride=65536,.k_batch_stride=kvheads*65536,
    .v_token_stride=256,.v_head_stride=65536,.v_batch_stride=kvheads*65536,
    .mask_batch_stride=0,.output_head_stride=512,.output_batch_stride=c->heads*512,
    .batches=1,.query_heads=c->heads,.kv_heads=kvheads,.kv_length=c->tokens,.head_dim=c->d,
    .scale=0x1.6a09e6p-4f};
  const uintptr_t bases[]={(uintptr_t)problem.query,(uintptr_t)problem.key,(uintptr_t)problem.value,
                           (uintptr_t)problem.mask,(uintptr_t)problem.output};
  const size_t sizes[]={problem.query_bytes,problem.key_bytes,problem.value_bytes,problem.mask_bytes,problem.output_bytes};
  for(unsigned i=0;i<5;++i) {
    const uintptr_t w=(uintptr_t)&workspace.value;
    if(!(w+sizeof(workspace.value)<=bases[i] || bases[i]+sizes[i]<=w))return AKV_STATUS_ALIAS;
  }
  context_t context={.c=c,.trial=trial,.device=&device,.index=index,.preflight=1};
  uint64_t preflight_groups=0;
  akv_status_t status=akv_decode_execute(&device,&problem,execute_group,&context,&preflight_groups);
  if(status!=AKV_STATUS_OK || preflight_groups!=kvheads)return AKV_STATUS_SHAPE;
  context.preflight=0;context.visited=0;
  return akv_decode_execute(&device,&problem,execute_group,&context,groups);
}
__attribute__((noinline,noclone)) void feature_terminal_marker(unsigned index) {
  __asm__ volatile("nop"::"r"(index):"memory");
}
int main(void) {
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb\nvsetivli zero,1,e32,m1,ta,ma\nvmv.v.i v0,0":"=r"(vlenb)::"v0","memory");
  drain();if(vlenb!=128){printf("FEATURE_FAIL vlenb=%lu\n",vlenb);return 1;}
  uint64_t errors=0;
  for(unsigned t=0;t<FEATURE_CALLS;++t) {
    const feature_trial_t *tr=&feature_trials[t];const feature_case_t *c=&feature_cases[tr->index];
    memset(&workspace,0xa5,sizeof(workspace));memset(&query,0xa5,sizeof(query));memset(&output,0xa5,sizeof(output));
    for(unsigned h=0;h<c->heads;++h)
      memcpy(query.value[h],feature_data+FEATURE_QUERY_F16_OFFSET+c->query_rows[h]*256,c->d*2);
    /* Identical captured F16 bytes are prepared before CSR initialization/ROI. */
    drain();
    const uintptr_t initial=(tr->frm<<5)|tr->initial_flags;
    __asm__ volatile("csrw fcsr,%0\ncsrwi vcsr,5\ncsrwi vstart,0"::"r"(initial):"memory");
    __asm__ volatile("frcsr %0":"=r"(results[t].initial_fcsr)::"memory");
    results[t].begin=cycles();
    const akv_status_t status=feature_full_call(t,&results[t].groups);
    results[t].returned=cycles();drain();results[t].end=cycles();
    __asm__ volatile("frcsr %0\ncsrr %1,vcsr\ncsrr %2,vstart"
        :"=r"(results[t].fcsr),"=r"(results[t].vcsr),"=r"(results[t].vstart)::"memory");
    feature_terminal_marker(t);
    results[t].query_hash=hash(UINT64_C(14695981039346656037),query.value,sizeof(query.value));
    results[t].guard_hash=guards(c,&results[t].guard_bytes);
    uint64_t expected_guard=UINT64_C(14695981039346656037);
    const unsigned char guard=0xa5;
    for(uint64_t i=0;i<results[t].guard_bytes;++i)expected_guard=hash(expected_guard,&guard,1);
    results[t].errors=status!=AKV_STATUS_OK || results[t].groups!=c->heads/c->rows ||
        results[t].initial_fcsr!=initial || results[t].vcsr!=5 || results[t].vstart ||
        (results[t].fcsr>>5)!=tr->frm || (results[t].fcsr&tr->initial_flags)!=tr->initial_flags ||
        (!tr->frm && results[t].fcsr!=(feature_flags[tr->index]|tr->initial_flags)) ||
        results[t].guard_hash!=expected_guard;
    for(unsigned h=0;h<c->heads;++h)
      for(unsigned d=0;d<c->d;++d)memcpy(&results[t].bits[h*c->d+d],&output.value[h][d],4);
    errors+=results[t].errors;
  }
  const uint64_t data_hash=hash(UINT64_C(14695981039346656037),feature_data,FEATURE_DATA_BYTES);
  errors+=data_hash!=FEATURE_DATA_HASH;
  for(unsigned t=0;t<FEATURE_CALLS;++t) {
    const feature_trial_t *tr=&feature_trials[t];const feature_case_t *c=&feature_cases[tr->index];
    printf("FEATURE_CALL trial=%u case=%u requested=%u frm=%u initial=%lu begin=%lu returned=%lu end=%lu fcsr=%lu vcsr=%lu vstart=%lu groups=%lu errors=%lu\n",
        t,tr->index,tr->requested,tr->frm,results[t].initial_fcsr,results[t].begin,results[t].returned,
        results[t].end,results[t].fcsr,results[t].vcsr,results[t].vstart,results[t].groups,results[t].errors);
    for(unsigned g=0;g<c->heads/c->rows;++g)
      printf("FEATURE_GROUP trial=%u group=%u first=%u rows=%u q=%lx k=%lx v=%lx out=%lx\n",t,g,
        results[t].group[g].first,results[t].group[g].rows,results[t].group[g].q,results[t].group[g].k,
        results[t].group[g].v,results[t].group[g].out);
    printf("FEATURE_MEMORY trial=%u query_hash=%lx guard_hash=%lx guard_bytes=%lu\n",t,
        results[t].query_hash,results[t].guard_hash,results[t].guard_bytes);
    for(unsigned i=0;i<c->heads*c->d;++i)printf("FEATURE_OUT trial=%u index=%u bits=%08x\n",t,i,results[t].bits[i]);
  }
  printf("FEATURE_DATA bytes=%u hash=%lx\n",FEATURE_DATA_BYTES,data_hash);
  printf("FEATURE_DONE calls=%u errors=%lu\n",FEATURE_CALLS,errors);
  return errors!=0;
}
