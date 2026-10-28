/* Reuse capture symbols and output checks without changing the running probe. */
#define main scheduler_probe_main
#include "native_main.c"
#undef main
#include "execute.h"

extern const uint16_t prefill_mask[];
static quant_prefill_workspace_t full_workspace;

int main(void) {
  qbs_device_t device;
  uintptr_t vlenb;__asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
  if(vlenb!=128 || qbs_device_query(qbs_native_info,NULL,&device)!=QBS_STATUS_OK) return 1;
  const unsigned row_bytes=prefill_q4?72:136;
  quant_prefill_input_t input={.tensors={
    .requested=1,.vlen_bits=1024,.normal_memory=1,.device=&device,
    .key_encoding=prefill_q4?QBS_WEIGHT_ENCODING_Q4_0:QBS_WEIGHT_ENCODING_Q8_0_WEIGHT,
    .value_encoding=QBS_WEIGHT_ENCODING_Q8_0_WEIGHT,
    .query={prefill_query+FIRST_QUERY*DIM,(40-FIRST_QUERY)*DIM*4,512,10240,DIM,4,2},
    .key={prefill_key,row_bytes*256,row_bytes,row_bytes*256,DIM,256,1},
    .value={prefill_value,136*256,136,136*256,DIM,256,1},
    .output={output.data,sizeof(output.data),2*STRIDE*4,STRIDE*4,DIM,4,2},
    .mask=prefill_mask+FIRST_QUERY*256,.mask_bytes=4*512,.scale=0},.mask_row_stride=512};
  input.tensors.scale=prefill_scale;
  akv_quant_native_bindings_t bindings={quantize_row_q8_0,dequantize_row_q8_0,
    quant_kv_ggml_scale_f32,quant_kv_ggml_mad_f32,qbs_native_execute_command,NULL};
  printf("PREFILL_SCOPE whole_call=1 admission=1 scatter=1 baseline=per_query_qbs\n");
  printf("PREFILL_CAP q4=%u rows=8 d=128 first_query=16 tokens=20 trials=4\n",prefill_q4);
  const unsigned order[]={0,1,1,0};
  for(unsigned trial=0;trial<4;++trial) {
    unsigned shared=order[trial];memset(&output,0xa5,sizeof(output));
    printf("PREFILL_BEGIN trial=%u shared=%u\n",trial,shared);
    __asm__ volatile("vsetivli zero,1,e32,m1,ta,ma\nvmv.v.i v8,0\ncsrwi fcsr,0\ncsrwi vcsr,5"
                     :::"memory","v8");
    drain();uint64_t begin=cycles();
    int status=0;unsigned calls=0,values=0;
    if(shared) {
      quant_prefill_report_t report;
      status=quant_prefill_execute(&input,&bindings,&full_workspace,sizeof(full_workspace),&report);
      calls=report.native.command_attempts;values=report.native.value_decodes;
      if(!status && (report.queries_quantized!=8 || report.native.completed_groups!=1 || report.key_panels)) status=3;
    } else {
      for(unsigned q=0;q<4 && !status;++q) {
        akv_quant_selection_input_t one=input.tensors;
        one.query.data=(const unsigned char *)one.query.data+q*one.query.token_stride;
        one.query.bytes-=q*one.query.token_stride;one.query.tokens=1;
        one.output.data=(const unsigned char *)one.output.data+q*one.output.token_stride;
        one.output.bytes-=q*one.output.token_stride;one.output.tokens=1;
        one.mask+=q*256;one.mask_bytes=512;
        akv_quant_native_report_t report;
        status=akv_quant_native_execute(&one,&bindings,&workspace,sizeof(workspace),&report);
        calls+=report.command_attempts;values+=report.value_decodes;
      }
    }
    drain();uint64_t elapsed=cycles()-begin;
    uintptr_t fc,vc;__asm__ volatile("frcsr %0;csrr %1,vcsr":"=r"(fc),"=r"(vc));
    unsigned errors=status || calls!=4 || values!=(shared?20:74) || fc>31 || vc!=5;
    if(!trial) baseline_fcsr=fc;else errors+=fc!=baseline_fcsr;
    for(unsigned row=0;row<ROWS;++row) {
      for(unsigned d=0;d<DIM;++d) {
        float y=output.data[row][d],gold=prefill_golden[((FIRST_QUERY+row/2)*16+row%2)*DIM+d];
        errors+=!isfinite(y) || !isfinite(gold) || fabsf(y-gold)>2e-5f+2e-5f*fabsf(gold);
        if(!trial) baseline[row][d]=y;else errors+=bits(y)!=bits(baseline[row][d]);
      }
      for(unsigned d=DIM;d<STRIDE;++d) errors+=bits(output.data[row][d])!=0xa5a5a5a5u;
    }
    for(unsigned i=0;i<64;++i) errors+=output.before[i]!=0xa5 || output.after[i]!=0xa5;
    printf("PREFILL_RESULT trial=%u shared=%u cycles=%lu commands=%u values=%u fcsr=%lu vcsr=%lu errors=%u hex=",
      trial,shared,(unsigned long)elapsed,calls,values,(unsigned long)fc,(unsigned long)vc,errors);
    for(unsigned row=0;row<ROWS;++row) for(unsigned d=0;d<DIM;++d) printf("%08x",bits(output.data[row][d]));
    printf("\n");if(errors) return 1;
  }
  printf("PREFILL_SUITE_PASS\n");return 0;
}
