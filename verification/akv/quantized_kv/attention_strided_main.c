/* Reuse frozen primitives, output guards and comparison helpers, not its main
 * or contiguous input callbacks. Both live schedules read the same strided KV. */
#include "software/akv/experimental/quantized_kv/ggml_decode.h"
#include "software/akv/experimental/quantized_kv/runtime_strided.h"
#include "software/akv/experimental/quantized_kv/q8_0_value.h"
#define main archived_main
#include "attention_main.c"
#undef main

extern const unsigned char attention_strided_key[], attention_strided_value[];
extern const uint16_t attention_mask[];
static struct ggml_tensor strided_q, strided_k, strided_v, strided_mask, strided_dst;
static unsigned char strided_scratch[16384] __attribute__((aligned(64)));
static float shared_previous[HEADS][DIM];

static __attribute__((noinline)) void strided_value_decode(const void *source,
    float *destination, int64_t elements) {
  akv_quant_q8_0_value(source, destination, (size_t)elements);
}

static int strided_baseline_qk(void *opaque, unsigned first_head, unsigned heads,
    unsigned first_token, unsigned tokens, float *scores, size_t stride) {
  context_t *c = opaque;
  if (heads != 1 || tokens != 1 || first_head >= HEADS || first_token >= TOKENS || stride < tokens)
    return 1;
  ++c->calls;
  const unsigned row = attention_key_kind ? 72 : 136;
  const void *key_row = attention_strided_key + first_token * 2u * row;
  if (attention_key_kind)
    ggml_vec_dot_q4_0_q8_0(DIM, scores, 0, key_row, 0, c->query[first_head], 0, 1);
  else
    ggml_vec_dot_q8_0_q8_0(DIM, scores, 0, key_row, 0, c->query[first_head], 0, 1);
  return 0;
}

static int strided_baseline_value(void *opaque, unsigned token, float *destination, unsigned dim) {
  context_t *c = opaque;
  if (token >= TOKENS || dim != DIM) return 1;
  ++c->values;
  strided_value_decode(attention_strided_value + token * 272u, destination, dim);
  return 0;
}

static uint64_t strided_cycles(void) {
  uint64_t result;
  __asm__ volatile("rdcycle %0" : "=r"(result) : : "memory");
  return result;
}

static void strided_tensor(struct ggml_tensor *t, enum ggml_type type, const void *data,
    unsigned d, unsigned tokens, unsigned heads, size_t block, size_t row, size_t head, size_t span) {
  memset(t, 0, sizeof(*t));
  t->type=type; t->data=(void *)data;
  t->ne[0]=d; t->ne[1]=tokens; t->ne[2]=heads; t->ne[3]=1;
  t->nb[0]=block; t->nb[1]=row; t->nb[2]=head; t->nb[3]=span;
}

int main(void) {
  __asm__ volatile("vsetivli zero,1,e32,m1,ta,ma\nvmv.v.i v8,0" : : : "v8", "memory");
  qbs_device_t device;
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
  const size_t scratch_bytes = akv_quant_strided_workspace_bytes();
  if (vlenb != 128 || scratch_bytes != 13120 || scratch_bytes > sizeof(strided_scratch) ||
      akv_quant_native_workspace_alignment() != 64 || attention_key_kind > 1 ||
      qbs_device_query(qbs_native_info, NULL, &device) != QBS_STATUS_OK) return 1;
  const unsigned key_row = attention_key_kind ? 72 : 136;
  strided_tensor(&strided_q, GGML_TYPE_F32, attention_query, DIM, 1, HEADS, 4, DIM*4, DIM*4, HEADS*DIM*4);
  /* Select KV head0 in a physical two-head allocation; token stride retains
   * the other real head, and mapping owns the complete backing extent. */
  strided_tensor(&strided_k, attention_key_kind ? GGML_TYPE_Q4_0 : GGML_TYPE_Q8_0,
      attention_strided_key, DIM, 256, 1, attention_key_kind ? 18 : 34, 2*key_row, key_row, 512*key_row);
  strided_tensor(&strided_v, GGML_TYPE_Q8_0, attention_strided_value, DIM, 256, 1, 34, 272, 136, 69632);
  strided_tensor(&strided_mask, GGML_TYPE_F16, attention_mask, 256, 1, 1, 2, 512, 512, 512);
  strided_tensor(&strided_dst, GGML_TYPE_F32, output.data, DIM, HEADS, 1,
      4, STRIDE*4, HEADS*STRIDE*4, sizeof(output.data));
  strided_dst.op = GGML_OP_FLASH_ATTN_EXT;
  strided_dst.src[0]=&strided_q; strided_dst.src[1]=&strided_k;
  strided_dst.src[2]=&strided_v; strided_dst.src[3]=&strided_mask;
  memcpy(strided_dst.op_params, &attention_scale, 4);
  akv_quant_ggml_context_t mapping={0};
  mapping.requested=1; mapping.nth=1; mapping.vlen_bits=(unsigned)vlenb*8;
  mapping.normal_memory=1; mapping.device=&device;
  mapping.query_bytes=HEADS*DIM*4; mapping.key_bytes=512*key_row;
  mapping.value_bytes=69632; mapping.mask_bytes=512; mapping.output_bytes=sizeof(output.data);
  const akv_quant_native_bindings_t bindings={quantize_row_q8_0, strided_value_decode,
      quant_kv_ggml_scale_f32, quant_kv_ggml_mad_f32, qbs_native_execute_command, NULL};
  printf("QUANT_STRIDED_CAP map_timed=1 admission_timed=1 gather_timed=1 workspace=%lu k_token_stride=%u v_token_stride=272\n",
      (unsigned long)scratch_bytes, 2*key_row);
  printf("QUANT_ATTN_CAP kind=%u heads=6 d=128 visible=128 kv_head=0 trials=4 scale=%08x\n",
      attention_key_kind, bits(attention_scale));
  const unsigned order[]={0,1,1,0};
  uintptr_t baseline_fcsr=0;
  for (unsigned trial=0; trial<4; ++trial) {
    memset(&output, 0xa5, sizeof(output)); memset(&context, 0, sizeof(context));
    printf("QUANT_ATTN_BEGIN trial=%u shared=%u\n", trial, order[trial]);
    /* A legal, defined v8 makes the pre-window global older-instruction drain
     * independent of a previous decoder's VL/vtype and register contents. */
    __asm__ volatile("vsetivli zero,1,e32,m1,ta,ma\nvmv.v.i v8,0\ncsrwi fcsr,0\ncsrwi vcsr,5"
                     : : : "v8", "memory");
    drain();
    const uint64_t start = strided_cycles();
    int status, map_status=0;
    akv_quant_strided_report_t report={0};
    if (order[trial]) {
      uintptr_t vstart, frm;
      __asm__ volatile("csrr %0,vstart;csrr %1,frm" : "=r"(vstart), "=r"(frm));
      mapping.vstart=(unsigned)vstart; mapping.frm=(unsigned)frm;
      akv_quant_selection_input_t input;
      map_status=akv_quant_ggml_map(&strided_dst, &mapping, &input);
      status=map_status ? AKV_QUANT_NATIVE_FALLBACK : akv_quant_strided_execute(
          &input, &bindings, strided_scratch, scratch_bytes, &report);
    } else {
      for (unsigned head=0; head<HEADS; ++head)
        quantize_row_q8_0(attention_query+head*DIM, context.query[head], DIM);
      const akv_quant_online_plan_t plan={HEADS,DIM,TOKENS,attention_scale,&context,
          strided_baseline_qk,strided_baseline_value,quant_kv_ggml_scale_f32,quant_kv_ggml_mad_f32};
      status=akv_quant_online_head_major(&plan, &output.data[0][0], STRIDE, &workspace);
    }
    drain();
    const uint64_t elapsed = strided_cycles()-start;
    uintptr_t fc, vc;
    __asm__ volatile("frcsr %0;csrr %1,vcsr" : "=r"(fc), "=r"(vc));
    const unsigned calls=order[trial] ? report.native.command_attempts : context.calls;
    const unsigned values=order[trial] ? report.native.value_decodes : context.values;
    if (!trial) baseline_fcsr=fc;
    unsigned errors=status!=0 || map_status!=0 || fc>31 || fc!=baseline_fcsr || vc!=5;
    errors+=calls!=(order[trial] ? 8u : HEADS*TOKENS) || values!=(order[trial] ? TOKENS : HEADS*TOKENS);
    if (order[trial]) {
      errors+=report.native.selection_reason!=0 || report.native.completed_groups!=1 ||
          report.native.executor_status!=QBS_STATUS_OK || report.key_panels!=4 || report.key_bytes!=TOKENS*key_row;
      printf("QUANT_STRIDED_ENTRY trial=%u map=%d status=%d selection=%u groups=%u commands=%u values=%u panels=%lu copied=%lu\n",
          trial,map_status,status,report.native.selection_reason,report.native.completed_groups,calls,values,
          (unsigned long)report.key_panels,(unsigned long)report.key_bytes);
    }
    float max_abs=0.0f, pair_max_abs=0.0f;
    unsigned pair_bits_differ=0;
    for (unsigned head=0; head<HEADS; ++head) {
      for (unsigned d=0; d<DIM; ++d) {
        const float y=output.data[head][d], gold=attention_golden[head*DIM+d];
        const float delta=fabsf(y-gold);
        errors+=!isfinite(y) || !isfinite(gold) || delta>0.004f+0.002f*fabsf(gold);
        if (delta>max_abs) max_abs=delta;
        if (!trial) baseline[head][d]=y;
        else {
          const float diff=fabsf(y-baseline[head][d]);
          if (diff>pair_max_abs) pair_max_abs=diff;
          pair_bits_differ+=bits(y)!=bits(baseline[head][d]);
          if (!order[trial]) errors+=bits(y)!=bits(baseline[head][d]);
        }
        if (trial==1) shared_previous[head][d]=y;
        if (trial==2) errors+=bits(y)!=bits(shared_previous[head][d]);
      }
      for (unsigned d=DIM; d<STRIDE; ++d) errors+=bits(output.data[head][d])!=UINT32_C(0xa5a5a5a5);
    }
    for (unsigned i=0; i<64; ++i) errors+=output.before[i]!=0xa5 || output.after[i]!=0xa5;
    printf("QUANT_ATTN_RESULT trial=%u shared=%u cycles=%lu calls=%u values=%u fcsr=%lu vcsr=%lu max_abs=%08x pair_max_abs=%08x pair_bits_differ=%u errors=%u hex=",
        trial,order[trial],(unsigned long)elapsed,calls,values,(unsigned long)fc,(unsigned long)vc,
        bits(max_abs),bits(pair_max_abs),pair_bits_differ,errors);
    for (unsigned head=0; head<HEADS; ++head)
      for (unsigned d=0; d<DIM; ++d) printf("%08x",bits(output.data[head][d]));
    printf("\n");
    if (errors) return 1;
  }
  printf("QUANT_ATTN_SUITE_PASS trials=4 outputs=768 golden_tolerance=1 ordinary_repeats_exact=1\n");
  return 0;
}
