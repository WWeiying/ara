/* No per-callback timers: use retirement PCs around one complete current call. */
#define main unused_scheduler_main
#include "native_main.c"
#undef main
#include "software/akv/experimental/quantized_kv/runtime_strided.h"

extern const uint16_t prefill_mask[];
static unsigned char profile_workspace[32768] __attribute__((aligned(64)));

int main(void) {
  qbs_device_t device;uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
  if(vlenb!=128 || qbs_device_query(qbs_native_info,NULL,&device)!=QBS_STATUS_OK ||
      akv_quant_strided_workspace_bytes()>sizeof(profile_workspace))return 1;
  const unsigned row_bytes=prefill_q4?72:136;
  akv_quant_selection_input_t input={
    .requested=1,.vlen_bits=1024,.normal_memory=1,.device=&device,
    .key_encoding=prefill_q4?QBS_WEIGHT_ENCODING_Q4_0:QBS_WEIGHT_ENCODING_Q8_0_WEIGHT,
    .value_encoding=QBS_WEIGHT_ENCODING_Q8_0_WEIGHT,
    .query={prefill_query+19*DIM,163840-19*DIM*4,512,10240,DIM,1,2},
    .key={prefill_key,row_bytes*256*8,row_bytes*8,row_bytes,DIM,256,1},
    .value={prefill_value,136*256*8,136*8,136,DIM,256,1},
    .output={output.data,sizeof(output.data),2*STRIDE*4,STRIDE*4,DIM,1,2},
    .mask=prefill_mask+19*256,.mask_bytes=512,.scale=prefill_scale};
  akv_quant_native_bindings_t bindings={quantize_row_q8_0,prefill_native_decode,
    quant_kv_ggml_scale_f32,quant_kv_ggml_mad_f32,qbs_native_execute_command,NULL};
  printf("DECODE_PROFILE_SCOPE query=19 heads=2 dim=128 visible=20 token_major=1 q4=%u\n",prefill_q4);
  memset(&output,0xa5,sizeof(output));
  __asm__ volatile("vsetivli zero,1,e32,m1,ta,ma\nvmv.v.i v8,0\ncsrwi fcsr,0\ncsrwi vcsr,5" :::"memory","v8");
  drain();uint64_t begin,end;
  __asm__ volatile(".global decode_profile_begin\ndecode_profile_begin:\nrdcycle %0":"=r"(begin)::"memory");
  akv_quant_strided_report_t report;
  int status=akv_quant_strided_execute(&input,&bindings,profile_workspace,sizeof(profile_workspace),&report);
  drain();
  __asm__ volatile(".global decode_profile_end\ndecode_profile_end:\nrdcycle %0":"=r"(end)::"memory");
  uintptr_t fc,vc;__asm__ volatile("frcsr %0;csrr %1,vcsr":"=r"(fc),"=r"(vc));
  unsigned errors=status || report.native.command_attempts!=1 || report.native.completed_groups!=1 ||
    report.native.value_decodes!=20 || report.key_panels!=1 || report.key_bytes!=20*row_bytes || fc>31 || vc!=5;
  for(unsigned row=0;row<ROWS;++row)for(unsigned d=0;d<STRIDE;++d) {
    float y=output.data[row][d];
    if(row<2 && d<DIM) {
      float gold=prefill_golden[(19*16+row)*DIM+d];
      errors+=!isfinite(y) || !isfinite(gold) || fabsf(y-gold)>2e-5f+2e-5f*fabsf(gold);
    } else errors+=bits(y)!=0xa5a5a5a5u;
  }
  for(unsigned i=0;i<64;++i)errors+=output.before[i]!=0xa5 || output.after[i]!=0xa5;
  printf("DECODE_PROFILE_RESULT cycles=%lu commands=%u groups=%u values=%u panels=%lu key_bytes=%lu fcsr=%lu vcsr=%lu errors=%u hex=",
    (unsigned long)(end-begin),report.native.command_attempts,report.native.completed_groups,
    report.native.value_decodes,(unsigned long)report.key_panels,(unsigned long)report.key_bytes,
    (unsigned long)fc,(unsigned long)vc,errors);
  for(unsigned row=0;row<2;++row)for(unsigned d=0;d<DIM;++d)printf("%08x",bits(output.data[row][d]));
  printf("\n");if(errors)return 1;
  printf("DECODE_PROFILE_PASS\n");return 0;
}
