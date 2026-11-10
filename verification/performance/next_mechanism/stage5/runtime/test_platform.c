/* Host policy/lease tests, not a validated instruction model or board provider. */
#include "platform.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static _Alignas(64) uint16_t query[8][256],key[137][256],value[137][256],mask[137];
static _Alignas(64) float output[8][256];
static _Alignas(64) unsigned char scratch[8192];
static akv_device_t device;
static akv_attention_plan_t plan;
static unsigned checks;
typedef struct {
  akv_platform_thread_state_v1 state;
  unsigned reads,acquires,releases,owned,allow,clobber;
} test_context;
static test_context ctx;

static akv_platform_result_t read_state(void *opaque,akv_platform_thread_state_v1 *s) {
  test_context *c=opaque;++c->reads;
  if(c->state.vstart)return AKV_PLATFORM_BAD_VSTART;
  *s=c->state;return AKV_PLATFORM_READY;
}
static uintptr_t acquire(void *opaque,const akv_platform_request_v1 *r) {
  test_context *c=opaque;++c->acquires;
  if(!c->allow || r->span_count!=6)return 0;
  assert(!c->owned);c->owned=1;
  if(c->clobber)c->state.fcsr^=1;
  return 0x1234;
}
static void release(void *opaque,uintptr_t cookie) {
  test_context *c=opaque;assert(cookie==0x1234 && c->owned);c->owned=0;++c->releases;
}
static akv_resident_platform_provider_v1 provider(void) {
  return (akv_resident_platform_provider_v1){
    .abi_version=1,.struct_bytes=sizeof(akv_resident_platform_provider_v1),
    .kind=AKV_PLATFORM_VALIDATED_TEST_MODEL,.assurances=AKV_PLATFORM_REQUIRED_ASSURANCES,
    .contract_sha256={1},.operation_mask=AKV_PLATFORM_QK_PV_V1,.qk_profile=1,.pv_profile=1,
    .nr_lanes=4,.vlen_bits=1024,.context=&ctx,.read_state=read_state,.acquire=acquire,.release=release};
}
static akv_platform_span_v1 spans[]={
  {query,sizeof(query),0},{key,sizeof(key),0},{value,sizeof(value),0},
  {mask,sizeof(mask),0},{output,sizeof(output),1},{scratch,sizeof(scratch),1}};
static akv_platform_request_v1 request(void) {
  return (akv_platform_request_v1){.abi_version=1,.struct_bytes=sizeof(akv_platform_request_v1),
    .requested=1,.workers=1,.decode_head_rows=1,.query_tokens=1,.groups=2,
    .spans=spans,.span_count=sizeof(spans)/sizeof(spans[0])};
}
static void reset(void) {
  ctx=(test_context){.state={128,0,8,5},.allow=1};memset(mask,0,sizeof(mask));
  assert(akv_device_init_reference(&device)==AKV_STATUS_OK);
}
static void make_plan(unsigned d,unsigned heads,unsigned t) {
  const akv_attention_problem_t p={
    .query=&query[0][0],.key=&key[0][0],.value=&value[0][0],.mask=mask,.output=&output[0][0],
    .q_row_stride_bytes=512,.k_token_stride_bytes=512,.v_token_stride_bytes=512,
    .output_row_stride_bytes=1024,.q_rows=heads,.head_dim=d,.kv_length=t,.scale=0.125f};
  assert(akv_attention_plan_create_v2(&device,&p,&plan)==AKV_STATUS_OK);
}
static void denied_provider(akv_resident_platform_provider_v1 *p) {
  akv_platform_request_v1 r=request();akv_platform_session_v1 s={0};
  assert(akv_resident_platform_admit_v1(p,&r,&s)==AKV_PLATFORM_KEEP_NATIVE);
  assert(!s.cookie && !ctx.reads && !ctx.acquires);++checks;
}
static void defaults_and_provider_fields(void) {
  reset();assert(akv_resident_platform_current_v1()==NULL);
  assert(akv_resident_platform_admit_v1(NULL,(const void *)1,(void *)1)==AKV_PLATFORM_KEEP_NATIVE);++checks;
  for(unsigned i=0;i<7;++i) {
    akv_resident_platform_provider_v1 p=provider();p.assurances^=1u<<i;denied_provider(&p);
  }
#define BAD(field,v) do {akv_resident_platform_provider_v1 p=provider();p.field=(v);denied_provider(&p);}while(0)
  BAD(abi_version,0);BAD(struct_bytes,1);BAD(kind,0);BAD(kind,3);BAD(operation_mask,1);
  BAD(qk_profile,0);BAD(pv_profile,0);BAD(nr_lanes,2);BAD(vlen_bits,512);
  BAD(read_state,NULL);BAD(acquire,NULL);BAD(release,NULL);
#undef BAD
  akv_resident_platform_provider_v1 p=provider();memset(p.contract_sha256,0,32);denied_provider(&p);
}
static void guards_before_copies(void) {
  reset();akv_resident_platform_provider_v1 p=provider();ctx.state.vstart=1;
  assert(akv_resident_platform_admit_v1(&p,(const void *)1,(void *)1)==AKV_PLATFORM_BAD_VSTART);
  assert(!ctx.acquires);++checks;
  reset();ctx.state.fcsr=40;
  assert(akv_resident_platform_admit_v1(&p,(const void *)1,(void *)1)==AKV_PLATFORM_KEEP_NATIVE);
  assert(!ctx.acquires);++checks;
  reset();ctx.state.vlenb=64;
  assert(akv_resident_platform_admit_v1(&p,(const void *)1,(void *)1)==AKV_PLATFORM_KEEP_NATIVE);++checks;
}
static void requests_and_leases(void) {
  reset();akv_resident_platform_provider_v1 p=provider();akv_platform_session_v1 s={0};
#define BAD(field,v) do {akv_platform_request_v1 r=request();r.field=(v);assert(akv_resident_platform_admit_v1(&p,&r,&s)==AKV_PLATFORM_KEEP_NATIVE);assert(!s.cookie && !ctx.acquires);++checks;}while(0)
  BAD(requested,0);BAD(workers,2);BAD(decode_head_rows,0);BAD(query_tokens,2);BAD(groups,0);
  BAD(refill_overlap,1);BAD(spans,NULL);BAD(span_count,0);
#undef BAD
  akv_platform_request_v1 r=request();ctx.allow=0;
  assert(akv_resident_platform_admit_v1(&p,&r,&s)==AKV_PLATFORM_KEEP_NATIVE && !s.cookie);++checks;
  ctx.allow=1;ctx.clobber=1;
  assert(akv_resident_platform_admit_v1(&p,&r,&s)==AKV_PLATFORM_INVALID && !s.cookie && !ctx.owned);
  assert(ctx.releases==1);++checks;
}
static void shapes_and_progress(void) {
  const unsigned ds[]={64,96,128},hs[]={1,2,3,8},ts[]={1,9,65,137};
  for(unsigned d=0;d<3;++d)for(unsigned h=0;h<4;++h)for(unsigned t=0;t<4;++t) {
    reset();make_plan(ds[d],hs[h],ts[t]);akv_resident_platform_provider_v1 p=provider();
    akv_platform_request_v1 r=request();akv_platform_session_v1 s={0};
    assert(akv_resident_platform_admit_v1(&p,&r,&s)==AKV_PLATFORM_READY);
    assert(akv_resident_platform_start_v1(&s)==AKV_PLATFORM_INVALID);
    akv_resident_attention_options_t opts={0};
    for(unsigned g=0;g<2;++g) {
      assert(akv_resident_platform_group_v1(&s,g,&device,&plan,NULL,&opts)==AKV_PLATFORM_READY);
      assert(opts.validated_available==1 && opts.platform_admitted==1 && opts.whole_call_owned==1);
      assert(akv_resident_attention_select(&device,&plan,&opts,0)==AKV_RESIDENT_USE_SHARED);
    }
    assert(akv_resident_platform_start_v1(&s)==AKV_PLATFORM_READY);
    assert(akv_resident_platform_group_v1(&s,2,(void *)1,(void *)1,(void *)1,(void *)1)==AKV_PLATFORM_NO_RETRY);
    assert(akv_resident_platform_start_v1(&s)==AKV_PLATFORM_NO_RETRY);
    akv_resident_platform_finish_v1(&s);akv_resident_platform_finish_v1(&s);
    assert(!ctx.owned && ctx.releases==1 && ctx.state.fcsr==8 && ctx.state.vcsr==5);++checks;
  }
}
static void group_rejections(void) {
  reset();make_plan(128,2,137);akv_resident_platform_provider_v1 p=provider();
  akv_platform_request_v1 r=request();akv_platform_session_v1 s={0};
  assert(akv_resident_platform_admit_v1(&p,&r,&s)==AKV_PLATFORM_READY);
  akv_resident_attention_options_t out,saved;memset(&out,0xa5,sizeof(out));saved=out;
  ctx.state.vstart=1;
  assert(akv_resident_platform_group_v1(&s,0,(void *)1,(void *)1,(void *)1,&out)==AKV_PLATFORM_BAD_VSTART);
  assert(memcmp(&out,&saved,sizeof(out))==0);ctx.state.vstart=0;++checks;
  akv_attention_features_t features={.sinks_enabled=1};
  assert(akv_resident_platform_group_v1(&s,0,&device,&plan,&features,&out)==AKV_PLATFORM_KEEP_NATIVE);++checks;
  mask[1]=0x3800;
  assert(akv_resident_platform_group_v1(&s,0,&device,&plan,NULL,&out)==AKV_PLATFORM_KEEP_NATIVE);mask[1]=0;++checks;
  const uintptr_t vbase=plan.descriptor.v_base;plan.descriptor.v_base=UINT64_C(0x90000000);
  assert(akv_resident_platform_group_v1(&s,0,&device,&plan,NULL,&out)==AKV_PLATFORM_KEEP_NATIVE);
  plan.descriptor.v_base=vbase;++checks;
  device.capabilities.token_axis_enabled=0;
  assert(akv_resident_platform_group_v1(&s,0,&device,&plan,NULL,&out)==AKV_PLATFORM_KEEP_NATIVE);++checks;
  assert(s.prepared==0 && memcmp(&out,&saved,sizeof(out))==0);
  akv_resident_platform_finish_v1(&s);assert(ctx.releases==1 && !ctx.owned);
  reset();make_plan(128,2,137);s=(akv_platform_session_v1){0};
  assert(akv_resident_platform_admit_v1(&p,&r,&s)==AKV_PLATFORM_READY);
  assert(akv_resident_platform_group_v1(&s,0,&device,&plan,NULL,&out)==AKV_PLATFORM_READY);
  mask[1]=0x3800;
  assert(akv_resident_platform_group_v1(&s,1,&device,&plan,NULL,&out)==AKV_PLATFORM_KEEP_NATIVE);
  assert(akv_resident_platform_start_v1(&s)==AKV_PLATFORM_INVALID && s.started==0);
  akv_resident_platform_finish_v1(&s);assert(ctx.releases==1 && !ctx.owned);++checks;
}
int main(void) {
  defaults_and_provider_fields();guards_before_copies();requests_and_leases();shapes_and_progress();group_rejections();
  assert(akv_resident_pv_capability_word(4,1)==0 && akv_resident_qk_capability_word(4,1)==0);
  printf("PLATFORM_HOST_PASS checks=%u native_execution=0 board_acceptance=0\n",checks);
  return 0;
}
