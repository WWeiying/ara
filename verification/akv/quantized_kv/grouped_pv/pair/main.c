/* Full native Attention ABBA. SDK integration is explicit in sdk_adapter.h. */
#include "verification/akv/quantized_kv/threeway_strided_primitives.h"
#include "sdk_adapter.h"

static unsigned pair_quantizations;

static void pair_quantize(const float *source, void *destination, int64_t n) {
  ++pair_quantizations;
  quantize_row_q8_0(source, destination, n);
}

static void pair_tensors(unsigned key_row, unsigned vlenb,
    const qbs_device_t *device, akv_quant_ggml_context_t *mapping) {
  strided_tensor(&strided_q, GGML_TYPE_F32, attention_query, DIM, 1, HEADS,
      4, DIM*4, DIM*4, HEADS*DIM*4);
  strided_tensor(&strided_k, attention_key_kind ? GGML_TYPE_Q4_0 : GGML_TYPE_Q8_0,
      attention_strided_key, DIM, 256, 1, attention_key_kind ? 18 : 34,
      2*key_row, key_row, 512*key_row);
  strided_tensor(&strided_v, GGML_TYPE_Q8_0, attention_strided_value, DIM,
      256, 1, 34, 272, 136, 69632);
  strided_tensor(&strided_mask, GGML_TYPE_F16, attention_mask, 256, 1, 1,
      2, 512, 512, 512);
  strided_tensor(&strided_dst, GGML_TYPE_F32, output.data, DIM, HEADS, 1,
      4, STRIDE*4, HEADS*STRIDE*4, sizeof(output.data));
  strided_dst.op=GGML_OP_FLASH_ATTN_EXT;
  strided_dst.src[0]=&strided_q; strided_dst.src[1]=&strided_k;
  strided_dst.src[2]=&strided_v; strided_dst.src[3]=&strided_mask;
  memcpy(strided_dst.op_params, &attention_scale, 4);
  memset(mapping, 0, sizeof(*mapping));
  mapping->requested=1; mapping->nth=1; mapping->vlen_bits=vlenb*8;
  mapping->normal_memory=1; mapping->device=device;
  mapping->query_bytes=HEADS*DIM*4; mapping->key_bytes=512*key_row;
  mapping->value_bytes=69632; mapping->mask_bytes=512;
  mapping->output_bytes=sizeof(output.data);
}

int main(void) {
  (void)strided_baseline_qk; (void)strided_baseline_value; (void)shared_previous;
  qbs_device_t device;
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
  const size_t scratch_bytes=akv_quant_strided_workspace_bytes();
  if (vlenb!=128 || scratch_bytes!=13120 || scratch_bytes>sizeof(strided_scratch) ||
      attention_key_kind!=1 || qbs_device_query(qbs_native_info,NULL,&device)!=QBS_STATUS_OK)
    return 1;
  akv_quant_ggml_context_t mapping;
  pair_tensors(72,(unsigned)vlenb,&device,&mapping);
  const akv_quant_native_bindings_t bindings={pair_quantize,strided_value_decode,
      quant_kv_ggml_scale_f32,quant_kv_ggml_mad_f32,qbs_native_execute_command,NULL};
  const unsigned order[]={0,1,1,0};
  uintptr_t first_fcsr=0;
  printf("QUANT_GROUPED_CAP kind=q4_0 heads=6 d=128 visible=128 kv_head=0 trials=4 scale=%08x k_token_stride=144 v_token_stride=272 workspace=%lu\n",
      bits(attention_scale),(unsigned long)scratch_bytes);
  for (unsigned trial=0; trial<4; ++trial) {
    const unsigned enabled=order[trial];
    memset(&output,0xa5,sizeof(output));
    pair_quantizations=0;
    printf("QUANT_GROUPED_BEGIN trial=%u enabled=%u api=%u\n",trial,enabled,enabled);
    __asm__ volatile("vsetivli zero,1,e32,m1,ta,ma\nvmv.v.i v8,0\ncsrwi fcsr,0\ncsrwi vcsr,5"
                     : : : "v8","memory");
    drain();
    const uint64_t start=strided_cycles();
    akv_quant_strided_report_t report={0};
    uintptr_t vstart,frm;
    __asm__ volatile("csrr %0,vstart;csrr %1,frm" : "=r"(vstart),"=r"(frm));
    mapping.vstart=(unsigned)vstart; mapping.frm=(unsigned)frm;
    akv_quant_selection_input_t input;
    const int map_status=akv_quant_ggml_map(&strided_dst,&mapping,&input);
    const int status=map_status ? AKV_QUANT_NATIVE_FALLBACK : pair_sdk_execute(
        enabled,&input,&bindings,strided_scratch,scratch_bytes,&report);
    drain();
    const uint64_t elapsed=strided_cycles()-start;
    uintptr_t fc,vc;
    __asm__ volatile("frcsr %0;csrr %1,vcsr" : "=r"(fc),"=r"(vc));
    if (!trial) first_fcsr=fc;
    unsigned errors=elapsed==0 || status!=0 || map_status!=0 || fc>31 || fc!=first_fcsr || vc!=5;
    errors+=pair_quantizations!=HEADS || report.native.command_attempts!=8 ||
        report.native.value_decodes!=128 || report.key_panels!=4 || report.key_bytes!=9216 ||
        report.native.selection_reason!=0 || report.native.completed_groups!=1 ||
        report.native.executor_status!=QBS_STATUS_OK;
    uint64_t hash=UINT64_C(14695981039346656037);
    float maximum=0.0f;
    unsigned differences=0;
    for (unsigned head=0; head<HEADS; ++head) {
      for (unsigned d=0; d<DIM; ++d) {
        const float y=output.data[head][d],gold=attention_golden[head*DIM+d];
        const float delta=fabsf(y-gold);
        errors+=!isfinite(y) || !isfinite(gold) || !isfinite(delta) || delta>0.004f+0.002f*fabsf(gold);
        if (delta>maximum) maximum=delta;
        if (!trial) baseline[head][d]=y;
        uint32_t word,expected;
        __builtin_memcpy(&word,&y,4); __builtin_memcpy(&expected,&baseline[head][d],4);
        differences+=word!=expected;
        for (unsigned byte=0; byte<4; ++byte)
          hash=(hash ^ ((word>>(8u*byte)) & 255u))*UINT64_C(1099511628211);
      }
      for (unsigned d=DIM; d<STRIDE; ++d) {
        uint32_t word;
        __builtin_memcpy(&word,&output.data[head][d],4);
        errors+=word!=UINT32_C(0xa5a5a5a5);
      }
    }
    for (unsigned i=0; i<64; ++i) errors+=output.before[i]!=0xa5 || output.after[i]!=0xa5;
    errors+=differences!=0;
    uint32_t maximum_word;
    __builtin_memcpy(&maximum_word,&maximum,4);
    printf("QUANT_GROUPED_RESULT trial=%u enabled=%u api=%u cycles=%lu commands=%u values=%u panels=%lu copied=%lu quantizations=%u map=%d status=%d selection=%u groups=%u executor=%u fcsr=%lu vcsr=%lu max_abs=%08x differences=%u errors=%u digest=%08x%08x\n",
        trial,enabled,enabled,(unsigned long)elapsed,report.native.command_attempts,report.native.value_decodes,
        (unsigned long)report.key_panels,(unsigned long)report.key_bytes,pair_quantizations,
        map_status,status,report.native.selection_reason,report.native.completed_groups,
        (unsigned)report.native.executor_status,(unsigned long)fc,(unsigned long)vc,maximum_word,
        differences,errors,(unsigned)(hash>>32),(unsigned)hash);
    if (errors) return 1;
  }
  printf("QUANT_GROUPED_SUITE_PASS trials=4 outputs=768 exact_all=1\n");
  return 0;
}
