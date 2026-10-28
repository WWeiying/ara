#define main unused_scheduler_main
#include "native_main.c"
#undef main
#include "execute_aligned.h"

extern const uint16_t prefill_mask[];
static quant_prefill_workspace_t plan_workspace;
static struct __attribute__((aligned(64))) {
  unsigned char before[64];float data[10][STRIDE];unsigned char after[64];
} plan_output;
static float plan_baseline[10][DIM];

extern void _fail(int) __attribute__((noreturn));
void __assert_func(const char *file,int line,const char *function,const char *expression) {
  printf("PREFILL_ASSERT_FAIL file=%s line=%d function=%s expression=%s\n",file,line,
    function?function:"",expression);
  _fail(1);
}

int main(void) {
  qbs_device_t device;uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
  if(vlenb!=128 || qbs_device_query(qbs_native_info,NULL,&device)!=QBS_STATUS_OK)return 1;
  unsigned row_bytes=prefill_q4?72:136;
  quant_prefill_input_t input={.tensors={
    .requested=1,.vlen_bits=1024,.normal_memory=1,.device=&device,
    .key_encoding=prefill_q4?QBS_WEIGHT_ENCODING_Q4_0:QBS_WEIGHT_ENCODING_Q8_0_WEIGHT,
    .value_encoding=QBS_WEIGHT_ENCODING_Q8_0_WEIGHT,
    .query={prefill_query,163840,512,10240,DIM,5,2},
    .key={prefill_key,row_bytes*256,row_bytes,row_bytes*256,DIM,256,1},
    .value={prefill_value,136*256,136,136*256,DIM,256,1},
    .output={plan_output.data,sizeof(plan_output.data),2*STRIDE*4,STRIDE*4,DIM,5,2},
    .mask=prefill_mask,.mask_bytes=5*512},.mask_row_stride=512};
  input.tensors.scale=prefill_scale;
  akv_quant_native_bindings_t bindings={quantize_row_q8_0,dequantize_row_q8_0,
    quant_kv_ggml_scale_f32,quant_kv_ggml_mad_f32,qbs_native_execute_command,NULL};
  printf("PREFILL_PLAN_SCOPE baseline=fixed_groups candidate=proven_alignment admission_in_roi=1\n");
  printf("PREFILL_CAP q4=%u rows=10 d=128 first_query=0 tokens=5 trials=4\n",prefill_q4);
  const unsigned order[]={0,1,1,0};
  for(unsigned trial=0;trial<4;++trial) {
    unsigned shared=order[trial];memset(&plan_output,0xa5,sizeof(plan_output));
    printf("PREFILL_BEGIN trial=%u shared=%u\n",trial,shared);
    __asm__ volatile("vsetivli zero,1,e32,m1,ta,ma\nvmv.v.i v8,0\ncsrwi fcsr,0\ncsrwi vcsr,5" :::"memory","v8");
    drain();uint64_t begin=cycles();quant_prefill_report_t report;
    int status=shared?quant_prefill_execute_aligned(&input,&bindings,&plan_workspace,sizeof(plan_workspace),&report):
                      quant_prefill_execute(&input,&bindings,&plan_workspace,sizeof(plan_workspace),&report);
    drain();uint64_t elapsed=cycles()-begin;uintptr_t fc,vc;
    __asm__ volatile("frcsr %0;csrr %1,vcsr":"=r"(fc),"=r"(vc));
    unsigned errors=status || report.native.command_attempts!=5 || report.native.value_decodes!=9 ||
      report.native.completed_groups!=2 || report.queries_quantized!=10 || report.key_panels || fc>31 || vc!=5;
    if(!trial)baseline_fcsr=fc;else errors+=fc!=baseline_fcsr;
    for(unsigned row=0;row<10;++row) {
      for(unsigned d=0;d<DIM;++d) {
        float y=plan_output.data[row][d],gold=prefill_golden[((row/2)*16+row%2)*DIM+d];
        errors+=!isfinite(y) || !isfinite(gold) || fabsf(y-gold)>2e-5f+2e-5f*fabsf(gold);
        if(!trial)plan_baseline[row][d]=y;else errors+=bits(y)!=bits(plan_baseline[row][d]);
      }
      for(unsigned d=DIM;d<STRIDE;++d)errors+=bits(plan_output.data[row][d])!=0xa5a5a5a5u;
    }
    for(unsigned i=0;i<64;++i)errors+=plan_output.before[i]!=0xa5 || plan_output.after[i]!=0xa5;
    printf("PREFILL_RESULT trial=%u shared=%u cycles=%lu commands=%u values=%u fcsr=%lu vcsr=%lu errors=%u hex=",
      trial,shared,(unsigned long)elapsed,report.native.command_attempts,report.native.value_decodes,
      (unsigned long)fc,(unsigned long)vc,errors);
    for(unsigned row=0;row<10;++row)for(unsigned d=0;d<DIM;++d)printf("%08x",bits(plan_output.data[row][d]));
    printf("\n");if(errors)return 1;
  }
  printf("PREFILL_SUITE_PASS\n");return 0;
}
