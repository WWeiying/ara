#include "value_cache_execute.h"
#include "printf.h"
#include "software/akv/experimental/quantized_kv/q8_0_value.h"

extern const float prefill_query[], prefill_golden[], prefill_scale;
extern const unsigned char prefill_key[], prefill_value[];
extern const uint16_t prefill_mask[];
extern const unsigned prefill_q4;
extern void quantize_row_q8_0(const float *, void *, int64_t);
extern void quant_kv_ggml_mad_f32(int, float *, const float *, float);
extern void quant_kv_ggml_scale_f32(int, float *, float);
static void prefill_native_decode(const void *source, float *out, int64_t n) {
  akv_quant_q8_0_value(source, out, (size_t)n);
}
enum { ROWS=16, DIM=128, STRIDE=136 };
static quant_prefill_workspace_t original_workspace;
static vcache_workspace_t cached_workspace;
static struct __attribute__((aligned(64))) {
  unsigned char before[64];
  float data[ROWS][STRIDE];
  unsigned char after[64];
} output;
static float baseline[ROWS][DIM];
static uint32_t bits(float f) { uint32_t b; memcpy(&b,&f,4); return b; }
static uint64_t cycles(void) { uint64_t c; __asm__ volatile("rdcycle %0":"=r"(c)); return c; }
static void drain(void) { __asm__ volatile("vmv.x.s zero,v8\nfence rw,rw":::"memory"); }

int main(void) {
  qbs_device_t device;
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
  if(vlenb!=128 || qbs_device_query(qbs_native_info,NULL,&device)!=QBS_STATUS_OK) return 1;
  const unsigned row_bytes=prefill_q4?72:136;
  quant_prefill_input_t input={.tensors={
    .requested=1,.vlen_bits=1024,.normal_memory=1,.device=&device,
    .key_encoding=prefill_q4?QBS_WEIGHT_ENCODING_Q4_0:QBS_WEIGHT_ENCODING_Q8_0_WEIGHT,
    .value_encoding=QBS_WEIGHT_ENCODING_Q8_0_WEIGHT,
    .query={prefill_query,40*DIM*4,512,10240,DIM,8,2},
    .key={prefill_key,row_bytes*256*8,row_bytes*8,row_bytes,DIM,256,1},
    .value={prefill_value,136*256*8,136*8,136,DIM,256,1},
    .output={output.data,sizeof(output.data),2*STRIDE*4,STRIDE*4,DIM,8,2},
    .mask=prefill_mask,.mask_bytes=8*512,.scale=0},.mask_row_stride=512};
  input.tensors.scale=prefill_scale;
  akv_quant_native_bindings_t bindings={quantize_row_q8_0,prefill_native_decode,
    quant_kv_ggml_scale_f32,quant_kv_ggml_mad_f32,qbs_native_execute_command,NULL};
  printf("VCACHE_SCOPE whole_call=1 admission=1 scatter=1 baseline=grouped_qbs\n");
  printf("VCACHE_LAYOUT token_major=1 physical_kv_heads=8 selected_head=0\n");
  printf("VCACHE_CAP q4=%u rows=16 d=128 first_query=0 tokens=8 trials=4\n",prefill_q4);
  const unsigned order[]={0,1,1,0};
  unsigned baseline_fcsr=0;
  for(unsigned trial=0;trial<4;++trial) {
    unsigned shared=order[trial];memset(&output,0xa5,sizeof(output));
    printf("VCACHE_BEGIN trial=%u shared=%u\n",trial,shared);
    __asm__ volatile("vsetivli zero,1,e32,m1,ta,ma\nvmv.v.i v8,0\ncsrwi fcsr,8\ncsrwi vcsr,5"
                     :::"memory","v8");
    drain();uint64_t begin=cycles();
    quant_prefill_report_t report;
    int status=shared ? vcache_execute(&input,&bindings,&cached_workspace,sizeof(cached_workspace),
                                       &report,prefill_native_decode) :
                        quant_prefill_execute(&input,&bindings,&original_workspace,sizeof(original_workspace),&report);
    drain();uint64_t elapsed=cycles()-begin;
    uintptr_t fc,vc;__asm__ volatile("frcsr %0;csrr %1,vcsr":"=r"(fc),"=r"(vc));
    unsigned errors=status || report.native.command_attempts!=8 ||
      report.native.value_decodes!=(shared?8u:12u) || fc>31 || !(fc&8) || vc!=5 ||
      report.queries_quantized!=16 || report.native.completed_groups!=2 ||
      report.key_panels!=2 || report.key_bytes!=12u*row_bytes;
    if(!trial) baseline_fcsr=fc; else errors+=fc!=baseline_fcsr;
    for(unsigned row=0;row<ROWS;++row) {
      for(unsigned d=0;d<DIM;++d) {
        float y=output.data[row][d],gold=prefill_golden[((row/2)*16+row%2)*DIM+d];
        errors+=!isfinite(y) || !isfinite(gold) || fabsf(y-gold)>2e-5f+2e-5f*fabsf(gold);
        if(!trial) baseline[row][d]=y; else errors+=bits(y)!=bits(baseline[row][d]);
      }
      for(unsigned d=DIM;d<STRIDE;++d) errors+=bits(output.data[row][d])!=0xa5a5a5a5u;
    }
    for(unsigned i=0;i<64;++i) errors+=output.before[i]!=0xa5 || output.after[i]!=0xa5;
    printf("VCACHE_PANEL trial=%u panels=%u key_bytes=%lu\n",trial,report.key_panels,(unsigned long)report.key_bytes);
    printf("VCACHE_RESULT trial=%u shared=%u cycles=%lu commands=%u values=%u fcsr=%lu vcsr=%lu errors=%u hex=",
      trial,shared,(unsigned long)elapsed,report.native.command_attempts,report.native.value_decodes,
      (unsigned long)fc,(unsigned long)vc,errors);
    for(unsigned row=0;row<ROWS;++row) for(unsigned d=0;d<DIM;++d) printf("%08x",bits(output.data[row][d]));
    printf("\n");if(errors) return 1;
  }
  printf("VCACHE_SUITE_PASS\n");return 0;
}
