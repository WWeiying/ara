/* Separate shared software scheduling from native QBS in one executable.
 * Frozen predecessor primitives are reused, not changed by this inquiry. */
#include "threeway_strided_primitives.h"
#include "shared_rvv_qk.h"

enum { MODE_HEAD_MAJOR, MODE_SHARED_RVV, MODE_QBS, THREEWAY_TRIALS = 6 };
static float mode_previous[3][HEADS][DIM];
static unsigned threeway_quantizations;

static void threeway_quantize(const float *source, void *destination, int64_t n) {
  ++threeway_quantizations;
  quantize_row_q8_0(source,destination,n);
}

static void threeway_tensors(unsigned key_row, unsigned vlenb,
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

typedef struct {
  shared_rvv_qk_context_t qk;
  unsigned values;
} threeway_context_t;

static __attribute__((noinline)) int threeway_qk(void *opaque, unsigned head, unsigned heads,
    unsigned token, unsigned tokens, float *scores, size_t stride) {
  threeway_context_t *c=opaque;
  return shared_rvv_qk(&c->qk, head, heads, token, tokens, scores, stride);
}

static int threeway_value(void *opaque, unsigned token, float *destination, unsigned dim) {
  threeway_context_t *c=opaque;
  if (token >= TOKENS || dim != DIM) return 1;
  ++c->values;
  strided_value_decode(attention_strided_value+token*272u, destination, dim);
  return 0;
}

int main(void) {
  /* Preserve an exact primitive-prefix copy without retaining its old paths. */
  (void)strided_baseline_qk; (void)strided_baseline_value; (void)shared_previous;
  qbs_device_t device;
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
  const size_t scratch_bytes=akv_quant_strided_workspace_bytes();
  if (vlenb!=128 || scratch_bytes!=13120 || scratch_bytes>sizeof(strided_scratch) ||
      attention_key_kind>1 || qbs_device_query(qbs_native_info,NULL,&device)!=QBS_STATUS_OK)
    return 1;
  const unsigned key_row=attention_key_kind ? 72 : 136;
  akv_quant_ggml_context_t mapping;
  threeway_tensors(key_row,(unsigned)vlenb,&device,&mapping);
  const akv_quant_native_bindings_t bindings={threeway_quantize,strided_value_decode,
      quant_kv_ggml_scale_f32,quant_kv_ggml_mad_f32,qbs_native_execute_command,NULL};
  /* Each mode appears at mirror positions, without comparisons across ELFs. */
  const unsigned order[]={MODE_HEAD_MAJOR,MODE_SHARED_RVV,MODE_QBS,
                          MODE_QBS,MODE_SHARED_RVV,MODE_HEAD_MAJOR};
  uintptr_t baseline_fcsr=0;
  unsigned seen[3]={0};
  printf("QUANT_THREEWAY_CAP kind=%u heads=6 d=128 visible=128 kv_head=0 trials=6 scale=%08x k_token_stride=%u v_token_stride=272 workspace=%lu\n",
      attention_key_kind,bits(attention_scale),2*key_row,(unsigned long)scratch_bytes);
  for (unsigned trial=0; trial<THREEWAY_TRIALS; ++trial) {
    const unsigned mode=order[trial];
    memset(&output,0xa5,sizeof(output)); memset(&context,0,sizeof(context));
    threeway_quantizations=0;
    threeway_context_t c={0};
    /* Query quantization is included once per head in every timed mode. */
    c.qk=(shared_rvv_qk_context_t){0};
    printf("QUANT_THREEWAY_BEGIN trial=%u mode=%u\n",trial,mode);
    __asm__ volatile("vsetivli zero,1,e32,m1,ta,ma\nvmv.v.i v8,0\ncsrwi fcsr,0\ncsrwi vcsr,5"
                     : : : "v8","memory");
    drain();
    const uint64_t start=strided_cycles();
    int status,map_status=0;
    akv_quant_strided_report_t report={0};
    if (mode==MODE_QBS) {
      uintptr_t vstart,frm;
      __asm__ volatile("csrr %0,vstart;csrr %1,frm" : "=r"(vstart),"=r"(frm));
      mapping.vstart=(unsigned)vstart; mapping.frm=(unsigned)frm;
      akv_quant_selection_input_t input;
      map_status=akv_quant_ggml_map(&strided_dst,&mapping,&input);
      status=map_status ? AKV_QUANT_NATIVE_FALLBACK : akv_quant_strided_execute(
          &input,&bindings,strided_scratch,scratch_bytes,&report);
    } else {
      for (unsigned head=0; head<HEADS; ++head)
        threeway_quantize(attention_query+head*DIM,context.query[head],DIM);
      /* Context initialization is deliberately inside the measurement window. */
      c.qk=(shared_rvv_qk_context_t){
          .key=attention_strided_key,.query=context.query,
          .key_bytes=512u*key_row,.query_bytes=sizeof(context.query),
          .token_stride=2u*key_row,.head_stride=key_row,.selectedkv=0,
          .query_stride=STRIDE,.key_row_bytes=key_row,.query_row_bytes=STRIDE,
          .dim=DIM,.heads=HEADS,.tokens=TOKENS,.kv_heads=2,
          .dot=attention_key_kind ? ggml_vec_dot_q4_0_q8_0 : ggml_vec_dot_q8_0_q8_0};
      const akv_quant_online_plan_t plan={HEADS,DIM,TOKENS,attention_scale,&c,
          threeway_qk,threeway_value,quant_kv_ggml_scale_f32,quant_kv_ggml_mad_f32};
      status=mode==MODE_SHARED_RVV ?
          akv_quant_online_shared(&plan,&output.data[0][0],STRIDE,&workspace) :
          akv_quant_online_head_major(&plan,&output.data[0][0],STRIDE,&workspace);
    }
    drain();
    const uint64_t elapsed=strided_cycles()-start;
    uintptr_t fc,vc;
    __asm__ volatile("frcsr %0;csrr %1,vcsr" : "=r"(fc),"=r"(vc));
    const unsigned calls=mode==MODE_QBS ? report.native.command_attempts : (unsigned)c.qk.callbacks;
    const unsigned dots=mode==MODE_QBS ? 0 : (unsigned)c.qk.dots;
    const unsigned commands=mode==MODE_QBS ? report.native.command_attempts : 0;
    const unsigned values=mode==MODE_QBS ? report.native.value_decodes : c.values;
    const size_t panels=mode==MODE_QBS ? report.key_panels : 0;
    const size_t copied=mode==MODE_QBS ? report.key_bytes : 0;
    if (!trial) baseline_fcsr=fc;
    unsigned errors=status!=0 || map_status!=0 || fc>31 || fc!=baseline_fcsr || vc!=5;
    errors+=threeway_quantizations!=HEADS;
    errors+=calls!=(mode==MODE_HEAD_MAJOR ? 768u : 8u) ||
        dots!=(mode==MODE_QBS ? 0u : 768u) || commands!=(mode==MODE_QBS ? 8u : 0u) ||
        values!=(mode==MODE_HEAD_MAJOR ? 768u : 128u) ||
        panels!=(mode==MODE_QBS ? 4u : 0u) || copied!=(mode==MODE_QBS ? TOKENS*key_row : 0u);
    if (mode==MODE_QBS)
      errors+=report.native.selection_reason!=0 || report.native.completed_groups!=1 ||
          report.native.executor_status!=QBS_STATUS_OK;
    float max_abs=0.0f,pair_max_abs=0.0f;
    unsigned differences=0;
    for (unsigned head=0; head<HEADS; ++head) {
      for (unsigned d=0; d<DIM; ++d) {
        const float y=output.data[head][d],gold=attention_golden[head*DIM+d];
        const float delta=fabsf(y-gold);
        errors+=!isfinite(y) || !isfinite(gold) || delta>0.004f+0.002f*fabsf(gold);
        if (delta>max_abs) max_abs=delta;
        if (!trial) baseline[head][d]=y;
        const float pair=fabsf(y-baseline[head][d]);
        if (pair>pair_max_abs) pair_max_abs=pair;
        differences+=bits(y)!=bits(baseline[head][d]);
        if (mode!=MODE_QBS) errors+=bits(y)!=bits(baseline[head][d]);
        if (seen[mode]) errors+=bits(y)!=bits(mode_previous[mode][head][d]);
        else mode_previous[mode][head][d]=y;
      }
      for (unsigned d=DIM; d<STRIDE; ++d)
        errors+=bits(output.data[head][d])!=UINT32_C(0xa5a5a5a5);
    }
    for (unsigned i=0; i<64; ++i) errors+=output.before[i]!=0xa5 || output.after[i]!=0xa5;
    ++seen[mode];
    printf("QUANT_THREEWAY_RESULT trial=%u mode=%u cycles=%lu calls=%u dots=%u commands=%u values=%u panels=%lu copied=%lu quantizations=%u map=%d status=%d selection=%u groups=%u executor=%u fcsr=%lu vcsr=%lu max_abs=%08x pair_max_abs=%08x pair_bits_differ=%u errors=%u hex=",
        trial,mode,(unsigned long)elapsed,calls,dots,commands,values,(unsigned long)panels,
        (unsigned long)copied,threeway_quantizations,map_status,status,
        report.native.selection_reason,report.native.completed_groups,
        (unsigned)report.native.executor_status,(unsigned long)fc,(unsigned long)vc,
        bits(max_abs),bits(pair_max_abs),differences,errors);
    for (unsigned head=0; head<HEADS; ++head)
      for (unsigned d=0; d<DIM; ++d) printf("%08x",bits(output.data[head][d]));
    printf("\n");
    if (errors) return 1;
  }
  printf("QUANT_THREEWAY_SUITE_PASS trials=6 outputs=768 rvv_exact=1 repeats_exact=1\n");
  return 0;
}
