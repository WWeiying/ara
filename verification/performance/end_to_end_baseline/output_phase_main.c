/* One captured Qwen2.5 KV group: original Output-Tile versus probed clone. */
#define main unused_prefill_main
#include "verification/akv/quantized_kv/prefill/native_main.c"
#undef main
#include "software/akv/experimental/quantized_kv/output_tile/runtime.h"
#include "output_phase_probe.h"

extern const uint16_t prefill_mask[];
extern int output_phase_execute(const akv_quant_selection_input_t *,
    const akv_quant_native_bindings_t *, void *, size_t, akv_quant_strided_report_t *);
extern size_t output_phase_workspace_bytes(void);

output_phase_stats_t output_phase_stats;
static unsigned char phase_workspace[32768] __attribute__((aligned(64)));

int main(void) {
  qbs_device_t device;
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
  if (vlenb != 128 || prefill_q4 ||
      qbs_device_query(qbs_native_info, NULL, &device) != QBS_STATUS_OK ||
      quant_output_tile_workspace_bytes() > sizeof(phase_workspace) ||
      output_phase_workspace_bytes() != quant_output_tile_workspace_bytes()) return 1;
  const akv_quant_selection_input_t input = {
    .requested=1, .vlen_bits=1024, .normal_memory=1, .device=&device,
    .key_encoding=QBS_WEIGHT_ENCODING_Q8_0_WEIGHT,
    .value_encoding=QBS_WEIGHT_ENCODING_Q8_0_WEIGHT,
    .query={prefill_query,12*DIM*4,DIM*4,DIM*4,DIM,1,6},
    .key={prefill_key,136*256*2,136*2,136,DIM,256,1},
    .value={prefill_value,136*256*2,136*2,136,DIM,256,1},
    .output={output.data,sizeof(output.data),6*STRIDE*4,STRIDE*4,DIM,1,6},
    .mask=prefill_mask, .mask_bytes=512, .scale=prefill_scale};
  const akv_quant_native_bindings_t bindings = {quantize_row_q8_0,prefill_native_decode,
    quant_kv_ggml_scale_f32,quant_kv_ggml_mad_f32,qbs_native_execute_command,NULL};
  const unsigned order[] = {0,1,1,0};
  const unsigned expected_calls[] = {1,1,4,4,4,1,8};
  const char *names[] = {"init","quantize","qk","coefficients","pv","finish","binding"};
  uintptr_t baseline_vc=0, baseline_start=0;
  printf("OUTPUT_PHASE_SCOPE model=qwen25 query=0 heads=6 kv=1 dim=128 visible=128 token_major=1 trials=4 whole_call=1 baseline=output_tile candidate=output_tile_probed\n");
  for (unsigned trial=0; trial<4; ++trial) {
    const unsigned probed=order[trial];
    memset(&output,0xa5,sizeof(output));
    memset(&output_phase_stats,0,sizeof(output_phase_stats));
    printf("OUTPUT_PHASE_BEGIN trial=%u probed=%u\n",trial,probed);
    __asm__ volatile("vsetivli zero,1,e32,m1,ta,ma\nvmv.v.i v8,0\n"
                     "csrwi fcsr,8\ncsrwi vcsr,5\ncsrwi vstart,0"
                     :::"memory","v8");
    const uint64_t begin=output_phase_stamp();
    akv_quant_strided_report_t report;
    const int status=probed ? output_phase_execute(&input,&bindings,phase_workspace,sizeof(phase_workspace),&report) :
      quant_output_tile_execute(&input,&bindings,phase_workspace,sizeof(phase_workspace),&report);
    const uint64_t elapsed=output_phase_stamp()-begin;
    uintptr_t fc,vc,start;
    __asm__ volatile("frcsr %0; csrr %1,vcsr; csrr %2,vstart"
        :"=r"(fc),"=r"(vc),"=r"(start)::"memory");
    unsigned errors=status || report.native.command_attempts!=8 ||
      report.native.completed_groups!=1 || report.native.value_decodes!=128 ||
      report.key_panels!=4 || report.key_bytes!=128*136 || fc!=9 || vc!=5 || start!=0;
    if (!trial) { baseline_fcsr=fc; baseline_vc=vc; baseline_start=start; }
    else errors+=fc!=baseline_fcsr || vc!=baseline_vc || start!=baseline_start;
    unsigned timer_reads=0;
    for (unsigned i=0; i<OUTPUT_PHASE_COUNT; ++i) {
      errors+=output_phase_stats.calls[i]!=(probed ? expected_calls[i] : 0);
      errors+=probed ? !output_phase_stats.cycles[i] : output_phase_stats.cycles[i]!=0;
      timer_reads+=2*output_phase_stats.calls[i];
    }
    for (unsigned row=0; row<ROWS; ++row) for (unsigned d=0; d<STRIDE; ++d) {
      const float y=output.data[row][d];
      if (row<6 && d<DIM) {
        const float gold=prefill_golden[row*DIM+d];
        errors+=!isfinite(y) || !isfinite(gold) || fabsf(y-gold)>2e-5f+2e-5f*fabsf(gold);
        if (!trial) baseline[row][d]=y;
        else errors+=bits(y)!=bits(baseline[row][d]);
      } else errors+=bits(y)!=0xa5a5a5a5u;
    }
    for (unsigned i=0; i<64; ++i) errors+=output.before[i]!=0xa5 || output.after[i]!=0xa5;
    printf("OUTPUT_PHASE_STATS trial=%u probed=%u timer_reads=%u",trial,probed,timer_reads);
    for (unsigned i=0; i<OUTPUT_PHASE_COUNT; ++i)
      printf(" %s_cycles=%lu %s_calls=%u",names[i],(unsigned long)output_phase_stats.cycles[i],
             names[i],output_phase_stats.calls[i]);
    printf("\nOUTPUT_PHASE_RESULT trial=%u probed=%u cycles=%lu commands=%u groups=%u values=%u panels=%lu key_bytes=%lu fcsr=%lu vcsr=%lu vstart=%lu errors=%u hex=",
      trial,probed,(unsigned long)elapsed,report.native.command_attempts,report.native.completed_groups,
      report.native.value_decodes,(unsigned long)report.key_panels,(unsigned long)report.key_bytes,
      (unsigned long)fc,(unsigned long)vc,(unsigned long)start,errors);
    for (unsigned row=0; row<6; ++row) for (unsigned d=0; d<DIM; ++d)
      printf("%08x",bits(output.data[row][d]));
    printf("\n");
    if (errors) { printf("OUTPUT_PHASE_FAIL\n"); return 1; }
  }
  printf("OUTPUT_PHASE_SUITE_PASS\n");
  return 0;
}
