#include "software/akv/experimental/quantized_kv/native.h"
#include "verification/qbs/qbs_ref.h"
#include <assert.h>
#include <stdio.h>

static float query[16][132], output[16][136], reference[16][136];
static unsigned char keys[2*65*136] __attribute__((aligned(64)));
static unsigned char values[2*65*136] __attribute__((aligned(64)));
static uint16_t mask[65];
static akv_quant_native_workspace_t workspace, reference_workspace;
static qbs_device_t device;
static unsigned quant_calls, decode_calls;
typedef struct { const akv_quant_selection_input_t *input; unsigned calls, fail_at, head_major_reference; } executor_t;

/* Unit-test quantizer: valid Q8_0 blocks with scale 1 and exact integer Query.
 * It checks binding/layout only; it is not a substitute for GGML's quantizer. */
static void quantize(const float *x, void *opaque, int64_t n) {
  unsigned char *out=opaque;
  ++quant_calls;
  for (int64_t first=0;first<n;first+=32,out+=34) {
    const uint16_t one=0x3c00; memcpy(out,&one,2);
    for (unsigned i=0;i<32;++i) {
      assert(x[first+i]>=-3 && x[first+i]<=3 && x[first+i]==(int)x[first+i]);
      out[2+i]=(unsigned char)(int8_t)x[first+i];
    }
  }
}

static void decode(const void *opaque, float *y, int64_t n) {
  const unsigned char *in=opaque;
  ++decode_calls;
  for (int64_t first=0;first<n;first+=32,in+=34) {
    uint16_t bits; memcpy(&bits,in,2); assert(bits==0x3c00 || bits==0x3800);
    for (unsigned i=0;i<32;++i) y[first+i]=(int8_t)in[2+i]*(bits==0x3c00?1.0f:0.5f);
  }
}
static void scale(int n,float *y,float s) { for(int i=0;i<n;++i) y[i]*=s; }
static void mad(int n,float *y,const float *x,float s) { for(int i=0;i<n;++i) y[i]=fmaf(x[i],s,y[i]); }

static qbs_status_t execute(void *opaque,const qbs_descriptor_t *descriptor,unsigned m,
    const void *activation,float *out,size_t stride,unsigned n,int segmented) {
  executor_t *e=opaque;
  ++e->calls;
  if (e->fail_at && e->calls==e->fail_at) return QBS_STATUS_EXECUTION;
  const qbs_descriptor_fields_t fields=qbs_unpack_descriptor_header(descriptor->header);
  const akv_quant_selection_input_t *p=e->input;
  assert(fields.activation_access==QBS_ACTIVATION_ACCESS_DIRECT && !segmented &&
         fields.n==n && fields.k_blocks==p->query.dim/32 && m<=4 && n<=32 && stride>=n);
  const size_t key_offset=descriptor->weight_base-(uintptr_t)p->key.data;
  const size_t head=key_offset/p->key.head_stride;
  const size_t token=(key_offset%p->key.head_stride)/p->key.token_stride;
  unsigned visible=0; while(visible<p->key.tokens && !p->mask[visible]) ++visible;
  assert(head<p->key.heads && token+n<=visible && key_offset%p->key.token_stride==0);
  float packed[128]; qbs_ref_result_t result;
  unsigned char aligned_query[4*8*34] __attribute__((aligned(64)));
  /* Head-major is an arithmetic reference, not an actual QBS submission. Its
   * odd Query row may be only two-byte aligned. The candidate must not need
   * this copy: groups4/2/1 always start at a legal command base. */
  if (!e->head_major_reference) assert(!((uintptr_t)activation&3u));
  if ((uintptr_t)activation&3u) {
    assert(e->head_major_reference);
    memcpy(aligned_query,activation,m*(p->query.dim/32)*34);
    activation=aligned_query;
  }
  const qbs_ref_status_t status=qbs_ref_execute(descriptor,m,8,1024,(uintptr_t)activation,
      (const void *)(uintptr_t)descriptor->weight_base,n*p->key.token_stride,activation,
      m*(p->query.dim/32)*34,packed,128,NULL,NULL,&result);
  if (status!=QBS_REF_OK) fprintf(stderr,"reference status=%u m=%u n=%u dim=%u token=%zu\n",
                                 (unsigned)status,m,n,p->query.dim,token);
  assert(status==QBS_REF_OK && !result.fflags);
  for(unsigned row=0;row<m;++row)
    memcpy(out+row*stride,packed+row*32,n*sizeof(float));
  return QBS_STATUS_OK;
}

static akv_quant_selection_input_t prepare(unsigned dim,unsigned heads,unsigned kvheads,unsigned visible,unsigned q4) {
  const size_t row=dim/32*(q4?18u:34u),vrow=dim/32*34u;
  memset(keys,0,sizeof(keys)); memset(values,0,sizeof(values));
  for(unsigned h=0;h<16;++h) for(unsigned d=0;d<132;++d) query[h][d]=(int)((h*3+d)%7)-3;
  for(unsigned h=0;h<kvheads;++h) for(unsigned t=0;t<65;++t)
    for(unsigned b=0;b<dim/32;++b) {
      unsigned char *k=keys+(h*65+t)*row+b*(q4?18:34);
      unsigned char *v=values+(h*65+t)*vrow+b*34;
      const uint16_t one=0x3c00, vs=t%2?0x3800:0x3c00;
      memcpy(k,&one,2); memcpy(v,&vs,2);
      if(q4) for(unsigned j=0;j<16;++j)
        k[2+j]=(unsigned char)(((h*7+t*3+b+j)%7+5)|(((h*7+t*3+b+j+16)%7+5)<<4));
      else for(unsigned j=0;j<32;++j) k[2+j]=(unsigned char)(int8_t)((int)((h*7+t*3+b+j)%7)-3);
      for(unsigned j=0;j<32;++j) v[2+j]=(unsigned char)(int8_t)((int)((t+h+j)%9)-4);
    }
  for(unsigned t=0;t<65;++t) mask[t]=t<visible?0:0xfc00;
  memset(output,0xa5,sizeof(output)); memset(reference,0xa5,sizeof(reference));
  quant_calls=decode_calls=0;
  return (akv_quant_selection_input_t){
    .requested=1,.vlen_bits=1024,.normal_memory=1,.device=&device,
    .key_encoding=q4?QBS_WEIGHT_ENCODING_Q4_0:QBS_WEIGHT_ENCODING_Q8_0_WEIGHT,
    .value_encoding=QBS_WEIGHT_ENCODING_Q8_0_WEIGHT,
    .query={query,sizeof(query),dim*4,sizeof(query[0]),dim,1,heads*kvheads},
    .key={keys,sizeof(keys),row,65*row,dim,65,kvheads},
    .value={values,sizeof(values),vrow,65*vrow,dim,65,kvheads},
    .output={output,sizeof(output),dim*4,sizeof(output[0]),dim,1,heads*kvheads},
    .mask=mask,.mask_bytes=sizeof(mask),.scale=0.03125f};
}

static void head_major(akv_quant_selection_input_t *p,akv_quant_native_bindings_t *b) {
  executor_t *executor=b->executor_context;
  executor->head_major_reference=1;
  akv_quant_selection_t selection; assert(akv_quant_select(p,&selection)==AKV_QUANT_SELECT_OK);
  akv_quant_native_report_t report={0};
  akv_quant_native_context_t context={p,b,&selection,&reference_workspace,&report,0};
  const akv_quant_online_plan_t plan={selection.group_heads,selection.dim,selection.visible_tokens,p->scale,
      &context,akv_quant_native_qk,akv_quant_native_value,b->scale,b->mad};
  for(unsigned h=0;h<selection.kv_heads;++h) {
    context.kv_head=h;
    for(unsigned q=0;q<selection.group_heads;++q)
      b->quantize(query[h*selection.group_heads+q],reference_workspace.query+q*selection.query_quant_row_bytes,selection.dim);
    assert(akv_quant_online_head_major(&plan,&reference[h*selection.group_heads][0],136,
                                     &reference_workspace.online)==AKV_QUANT_OK);
  }
  executor->head_major_reference=0;
}

int main(void) {
  assert(akv_quant_native_workspace_bytes()==sizeof(workspace) &&
         akv_quant_native_workspace_alignment()==64);
  assert(qbs_device_init_reference(1024,&device)==QBS_STATUS_OK);
  const unsigned dims[]={32,96,128},groups[]={1,3,6,7},prefixes[]={1,33};
  unsigned cases=0;
  for(unsigned d=0;d<3;++d) for(unsigned h=0;h<4;++h) for(unsigned k=1;k<=2;++k)
    for(unsigned t=0;t<2;++t) for(unsigned q4=0;q4<2;++q4) {
      akv_quant_selection_input_t p=prepare(dims[d],groups[h],k,prefixes[t],q4);
      executor_t executor={.input=&p};
      akv_quant_native_bindings_t bindings={quantize,decode,scale,mad,execute,&executor};
      head_major(&p,&bindings);
      executor.calls=quant_calls=decode_calls=0;
      akv_quant_native_report_t report;
      assert(akv_quant_native_execute(&p,&bindings,&workspace,sizeof(workspace),&report)==AKV_QUANT_NATIVE_OK);
      assert(report.selection_reason==AKV_QUANT_SELECT_OK && report.completed_groups==k &&
             quant_calls==groups[h]*k && report.value_decodes==k*prefixes[t] && decode_calls==report.value_decodes);
      const unsigned per_tile=groups[h]/4+(groups[h]%4>=2)+(groups[h]%2);
      assert(report.command_attempts==k*((prefixes[t]+31)/32)*per_tile && executor.calls==report.command_attempts);
      assert(memcmp(output,reference,sizeof(output))==0); ++cases;
    }
  akv_quant_selection_input_t p=prepare(128,6,2,33,0);
  executor_t executor={.input=&p,.fail_at=1};
  akv_quant_native_bindings_t bindings={quantize,decode,scale,mad,execute,&executor};
  akv_quant_native_report_t report;
  p.requested=0;
  assert(akv_quant_native_execute(&p,&bindings,&workspace,sizeof(workspace),&report)==AKV_QUANT_NATIVE_FALLBACK &&
         !executor.calls && !quant_calls && !decode_calls);
  for(size_t i=0;i<sizeof(output);++i) assert(((unsigned char *)output)[i]==0xa5);
  p.requested=1;
  assert(akv_quant_native_execute(&p,&bindings,&workspace,sizeof(workspace),&report)==AKV_QUANT_NATIVE_EXECUTION_FAILED &&
         executor.calls==1 && report.command_attempts==1 && report.completed_groups==0 &&
         report.executor_status==QBS_STATUS_EXECUTION && quant_calls==6 && !decode_calls);
  p=prepare(128,6,2,33,0); executor.calls=0; executor.fail_at=5;
  assert(akv_quant_native_execute(&p,&bindings,&workspace,sizeof(workspace),&report)==AKV_QUANT_NATIVE_EXECUTION_FAILED &&
         report.completed_groups==1 && report.command_attempts==5 && report.value_decodes==33 && quant_calls==12);
  p=prepare(128,6,1,33,0); executor.calls=0; executor.fail_at=0;
  memset(&workspace,0xa5,sizeof(workspace));
  p.output.data=&workspace; p.output.bytes=sizeof(workspace);
  assert(akv_quant_native_execute(&p,&bindings,&workspace,sizeof(workspace),&report)==AKV_QUANT_NATIVE_FALLBACK &&
         report.selection_reason==AKV_QUANT_SELECT_ALIAS && !quant_calls && !executor.calls);
  for(size_t i=0;i<sizeof(workspace);++i) assert(((unsigned char *)&workspace)[i]==0xa5);
  p=prepare(128,6,2,33,0); executor.calls=0;
  assert(akv_quant_native_execute(&p,&bindings,&workspace,sizeof(workspace)-1,&report)==AKV_QUANT_NATIVE_FALLBACK &&
         report.selection_reason==AKV_QUANT_SELECT_LAYOUT && !quant_calls && !executor.calls);
  const uint32_t snan=0x7f800001u; const uint16_t bad_scale=0x7c01;
  for(unsigned condition=0;condition<4;++condition) {
    p=prepare(128,6,2,33,0); executor.calls=0;
    if(condition==0) memcpy(&query[11][0],&snan,4);
    if(condition==1) memcpy(keys+(65+32)*136,&bad_scale,2);
    if(condition==2) memcpy(values+(65+32)*136,&bad_scale,2);
    if(condition==3) mask[34]=0;
    assert(akv_quant_native_execute(&p,&bindings,&workspace,sizeof(workspace),&report)==AKV_QUANT_NATIVE_FALLBACK &&
           !quant_calls && !decode_calls && !executor.calls && !report.command_attempts && !report.completed_groups);
    for(size_t i=0;i<sizeof(output);++i) assert(((unsigned char *)output)[i]==0xa5);
  }
  printf("QUANT_NATIVE_HOST_PASS cases=%u reference=qbs_ref test_quantizer=integer_scale1 padding=1 fallback_before_callbacks=1 execution_failure_no_retry=1\n",cases);
  return 0;
}
