#include "execute_planned.h"
#include "verification/qbs/qbs_ref.h"
#include <assert.h>
#include <fenv.h>
#include <stdio.h>
#include <stdlib.h>

extern void prefill_host_init(void);
extern void prefill_host_quantize(const float *,void *,int64_t);
extern void prefill_host_decode(const void *,float *,int64_t);
extern void prefill_host_scale(int,float *,float);
extern void prefill_host_mad(int,float *,const float *,float);
static quant_prefill_workspace_t workspace;
static akv_quant_native_workspace_t old_workspace;
static unsigned commands;

static void *load(const char *root,const char *name,size_t bytes) {
  char path[4096];int n=snprintf(path,sizeof(path),"%s/%s",root,name);
  assert(n>0 && (size_t)n<sizeof(path));
  FILE *f=fopen(path,"rb");assert(f);void *data=malloc(bytes);assert(data);
  assert(fread(data,1,bytes,f)==bytes && fgetc(f)==EOF);assert(!fclose(f));return data;
}
static qbs_status_t reference_execute(void *context,const qbs_descriptor_t *desc,
    unsigned m,const void *activation,float *out,size_t stride,unsigned n,int segmented) {
  (void)context;assert(!segmented && m<=4 && n<=32 && stride>=n);
  qbs_descriptor_fields_t f=qbs_unpack_descriptor_header(desc->header);
  assert(f.n==n && f.k_blocks==4);
  size_t block=f.weight_profile==QBS_WEIGHT_PROFILE_Q4_0 ? 18 : 34;
  assert(f.weight_profile==QBS_WEIGHT_PROFILE_Q4_0 || f.weight_profile==QBS_WEIGHT_PROFILE_Q8_0_WEIGHT);
  float packed[128];qbs_ref_result_t report;
  assert(qbs_ref_execute(desc,m,8,1024,(uintptr_t)activation,(void *)(uintptr_t)desc->weight_base,
      n*4*block,activation,m*136,packed,128,NULL,NULL,&report)==QBS_REF_OK);
  for(unsigned row=0;row<m;++row) memcpy(out+row*stride,packed+row*32,n*4);
  ++commands;return QBS_STATUS_OK;
}
int main(int argc,char **argv) {
  assert(argc==3 && (!strcmp(argv[2],"q4_0") || !strcmp(argv[2],"q8_0")));
  prefill_host_init();
  unsigned q4=!strcmp(argv[2],"q4_0"),row=q4?72:136;
  void *q=load(argv[1],"attn_q_input-0.bin",163840);
  void *k=load(argv[1],"attn_k_input-0.bin",row*256*8);
  void *v=load(argv[1],"attn_v_input-0.bin",278528);
  uint16_t *mask=load(argv[1],"attn_mask_input-0.bin",10240);
  float *gold=load(argv[1],"kqv_out-0.bin",163840);
  float *output=malloc(163840),*baseline=malloc(163840);assert(output && baseline);
  qbs_device_t device;assert(qbs_device_init_reference(1024,&device)==QBS_STATUS_OK);
  quant_prefill_input_t request={.tensors={
    .requested=1,.vlen_bits=1024,.normal_memory=1,.device=&device,
    .key_encoding=q4?QBS_WEIGHT_ENCODING_Q4_0:QBS_WEIGHT_ENCODING_Q8_0_WEIGHT,
    .value_encoding=QBS_WEIGHT_ENCODING_Q8_0_WEIGHT,
    .query={q,163840,512,10240,128,5,16},.key={k,row*256*8,row,row*256,128,256,8},
    .value={v,278528,136,34816,128,256,8},
    .output={output,163840,8192,512,128,5,16},.mask=mask,.mask_bytes=10240},.mask_row_stride=512};
  uint32_t scale=0x3db504f3;memcpy(&request.tensors.scale,&scale,4);
  akv_quant_native_bindings_t bindings={prefill_host_quantize,prefill_host_decode,
    prefill_host_scale,prefill_host_mad,reference_execute,NULL};
  feclearexcept(FE_ALL_EXCEPT);
  for(unsigned t=0;t<5;++t) {
    akv_quant_selection_input_t slice=request.tensors;
    slice.query.data=(unsigned char *)q+t*512;slice.query.bytes-=t*512;slice.query.tokens=1;
    slice.output.data=baseline+t*2048;slice.output.bytes-=t*8192;slice.output.tokens=1;
    slice.mask=mask+t*256;slice.mask_bytes=512;
    akv_quant_native_report_t report;
    assert(akv_quant_native_execute(&slice,&bindings,&old_workspace,sizeof(old_workspace),&report)==AKV_QUANT_NATIVE_OK);
  }
  int old_flags=fetestexcept(FE_ALL_EXCEPT);assert(commands==40);
  unsigned char *padded=malloc((row+8)*256*8);assert(padded);memset(padded,0xa5,(row+8)*256*8);
  for(unsigned h=0;h<8;++h) for(unsigned t=0;t<256;++t)
    memcpy(padded+(h*256+t)*(row+8),(unsigned char *)k+(h*256+t)*row,row);
  for(unsigned strided=0;strided<2;++strided) {
    if(strided) request.tensors.key=(akv_quant_tensor_view_t){padded,(row+8)*256*8,row+8,(row+8)*256,128,256,8};
    commands=0;feclearexcept(FE_ALL_EXCEPT);
    quant_prefill_report_t fixed;
    assert(quant_prefill_execute(&request,&bindings,&workspace,sizeof(workspace),&fixed)==AKV_QUANT_NATIVE_OK);
    assert(commands==40 && fixed.native.value_decodes==72 && fixed.native.completed_groups==16);
    assert(fixed.key_panels==(strided?16:0) && fixed.key_bytes==(strided?72*row:0));
    assert(fetestexcept(FE_ALL_EXCEPT)==old_flags && !memcmp(output,baseline,40960));
    memset(output,0xa5,163840);commands=0;feclearexcept(FE_ALL_EXCEPT);
    quant_prefill_report_t report;
    assert(quant_prefill_execute_planned(&request,&bindings,&workspace,sizeof(workspace),&report)==AKV_QUANT_NATIVE_OK);
    assert(fetestexcept(FE_ALL_EXCEPT)==old_flags && !memcmp(output,baseline,40960));
    assert(commands==40 && report.native.command_attempts==40 && report.queries_quantized==80 &&
           report.native.completed_groups==16 && report.native.value_decodes==48 &&
           report.key_panels==(strided?16:0) && report.key_bytes==(strided?48*row:0));
    for(unsigned i=40960;i<163840;++i) assert(((unsigned char *)output)[i]==0xa5);
    double maximum=0;
    for(unsigned i=0;i<10240;++i) {
      double error=fabs((double)output[i]-gold[i]);
      assert(isfinite(output[i]) && isfinite(gold[i]) && error<=2e-5+2e-5*fabs((double)gold[i]));
      if(error>maximum) maximum=error;
    }
    printf("REAL_PREFILL_PLANNED_PASS key=%s strided=%u outputs=10240 commands=%u groups=%u value_decodes=%u key_bytes=%zu max_abs=%.9g hardware=not_executed\n",
      argv[2],strided,commands,report.native.completed_groups,report.native.value_decodes,report.key_bytes,maximum);
  }
  free(q);free(k);free(v);free(mask);free(gold);free(output);free(baseline);free(padded);
}
