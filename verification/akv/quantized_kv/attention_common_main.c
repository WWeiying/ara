/* Preserve the sealed original primitives, tensors, comparison helpers and
 * ordinary schedule. Only the candidate now enters through the public ABI. */
#include "software/akv/experimental/quantized_kv/ggml_decode.h"
#define main archived_attention_main
#include "attention_main.c"
#undef main

extern const uint16_t attention_mask[];
static struct ggml_tensor common_q,common_k,common_v,common_mask,common_dst;
/* Bounded test storage, not an additional hardware memory. Only the public
 * runtime-reported bytes are passed to execution; excess capacity is unused. */
static unsigned char common_scratch[8192] __attribute__((aligned(64)));

static uint64_t common_cycles(void) {
  uint64_t result;
  __asm__ volatile("rdcycle %0" : "=r"(result) : : "memory");
  return result;
}

static void common_tensor(struct ggml_tensor *t,enum ggml_type type,const void *data,
    unsigned d,unsigned tokens,unsigned heads,size_t block,size_t row,size_t head) {
  memset(t,0,sizeof(*t)); t->type=type; t->data=(void *)data;
  t->ne[0]=d; t->ne[1]=tokens; t->ne[2]=heads; t->ne[3]=1;
  t->nb[0]=block; t->nb[1]=row; t->nb[2]=head; t->nb[3]=head*heads;
}

int main(void) {
  __asm__ volatile("vsetivli zero,1,e32,m1,ta,ma" : : : "memory");
  qbs_device_t device;
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
  const size_t scratch_bytes=akv_quant_native_workspace_bytes();
  if(vlenb!=128 || scratch_bytes>sizeof(common_scratch) ||
      akv_quant_native_workspace_alignment()!=64 ||
      qbs_device_query(qbs_native_info,NULL,&device)!=QBS_STATUS_OK) return 1;
  const unsigned key_row=attention_key_kind ? 72 : 136;
  common_tensor(&common_q,GGML_TYPE_F32,attention_query,DIM,1,HEADS,4,DIM*4,DIM*4);
  common_tensor(&common_k,attention_key_kind ? GGML_TYPE_Q4_0 : GGML_TYPE_Q8_0,
                attention_key,DIM,256,1,attention_key_kind ? 18 : 34,key_row,256*key_row);
  common_tensor(&common_v,GGML_TYPE_Q8_0,attention_value,DIM,256,1,34,136,34816);
  common_tensor(&common_mask,GGML_TYPE_F16,attention_mask,256,1,1,2,512,512);
  common_tensor(&common_dst,GGML_TYPE_F32,output.data,DIM,HEADS,1,4,STRIDE*4,HEADS*STRIDE*4);
  common_dst.op=GGML_OP_FLASH_ATTN_EXT;
  common_dst.src[0]=&common_q; common_dst.src[1]=&common_k;
  common_dst.src[2]=&common_v; common_dst.src[3]=&common_mask;
  memcpy(common_dst.op_params,&attention_scale,4);
  akv_quant_ggml_context_t mapping={0};
  mapping.requested=1; mapping.nth=1; mapping.vlen_bits=(unsigned)vlenb*8;
  mapping.normal_memory=1; mapping.device=&device;
  mapping.query_bytes=HEADS*DIM*4; mapping.key_bytes=256*key_row;
  mapping.value_bytes=34816; mapping.mask_bytes=512; mapping.output_bytes=sizeof(output.data);
  const akv_quant_native_bindings_t bindings={quantize_row_q8_0,dequantize_row_q8_0,
      quant_kv_ggml_scale_f32,quant_kv_ggml_mad_f32,qbs_native_execute_command,NULL};
  printf("QUANT_COMMON_CAP map_timed=1 admission_timed=1 workspace=%lu\n",(unsigned long)scratch_bytes);
  printf("QUANT_ATTN_CAP kind=%u heads=6 d=128 visible=128 kv_head=0 trials=4 scale=%08x\n",
         attention_key_kind,bits(attention_scale));
  const unsigned order[]={0,1,1,0};
  for(unsigned trial=0;trial<4;++trial) {
    memset(&output,0xa5,sizeof(output)); memset(&context,0,sizeof(context));
    context.shared=0;
    printf("QUANT_ATTN_BEGIN trial=%u shared=%u\n",trial,order[trial]);
    __asm__ volatile("csrwi fcsr,0;csrwi vcsr,5" : : : "memory");
    drain();
    const uint64_t start=common_cycles();
    int status,map_status=0;
    akv_quant_native_report_t report={0};
    if(order[trial]) {
      uintptr_t vstart,frm;
      __asm__ volatile("csrr %0,vstart;csrr %1,frm" : "=r"(vstart),"=r"(frm));
      mapping.vstart=(unsigned)vstart; mapping.frm=(unsigned)frm;
      akv_quant_selection_input_t input;
      map_status=akv_quant_ggml_map(&common_dst,&mapping,&input);
      status=map_status ? AKV_QUANT_NATIVE_FALLBACK : akv_quant_native_execute(
          &input,&bindings,common_scratch,scratch_bytes,&report);
    } else {
      for(unsigned head=0;head<HEADS;++head)
        quantize_row_q8_0(attention_query+head*DIM,context.query[head],DIM);
      const akv_quant_online_plan_t plan={HEADS,DIM,TOKENS,attention_scale,&context,qk,value,
          quant_kv_ggml_scale_f32,quant_kv_ggml_mad_f32};
      status=akv_quant_online_head_major(&plan,&output.data[0][0],STRIDE,&workspace);
    }
    drain();
    const uint64_t elapsed=common_cycles()-start;
    uintptr_t fc,vc;
    __asm__ volatile("frcsr %0;csrr %1,vcsr" : "=r"(fc),"=r"(vc));
    const unsigned calls=order[trial] ? report.command_attempts : context.calls;
    const unsigned values=order[trial] ? report.value_decodes : context.values;
    unsigned errors=status!=0 || map_status!=0 || fc>31 || vc!=5;
    errors+=calls!=(order[trial] ? 8u : HEADS*TOKENS) || values!=(order[trial] ? TOKENS : HEADS*TOKENS);
    if(order[trial]) {
      errors+=report.selection_reason!=0 || report.completed_groups!=1 || report.executor_status!=QBS_STATUS_OK;
      printf("QUANT_COMMON_ENTRY trial=%u map=%d status=%d selection=%u groups=%u commands=%u values=%u\n",
          trial,map_status,status,report.selection_reason,report.completed_groups,calls,values);
    }
    float max_abs=0.0f,pair_max_abs=0.0f;
    unsigned pair_bits_differ=0;
    for(unsigned head=0;head<HEADS;++head) {
      for(unsigned d=0;d<DIM;++d) {
        const float y=output.data[head][d],gold=attention_golden[head*DIM+d];
        const float delta=fabsf(y-gold);
        errors+=!isfinite(y) || !isfinite(gold) || delta>0.004f+0.002f*fabsf(gold);
        if(delta>max_abs) max_abs=delta;
        if(!trial) baseline[head][d]=y;
        else {
          const float diff=fabsf(y-baseline[head][d]);
          if(diff>pair_max_abs) pair_max_abs=diff;
          pair_bits_differ+=bits(y)!=bits(baseline[head][d]);
          if(!order[trial]) errors+=bits(y)!=bits(baseline[head][d]);
        }
      }
      for(unsigned d=DIM;d<STRIDE;++d) errors+=bits(output.data[head][d])!=UINT32_C(0xa5a5a5a5);
    }
    for(unsigned i=0;i<64;++i) errors+=output.before[i]!=0xa5 || output.after[i]!=0xa5;
    printf("QUANT_ATTN_RESULT trial=%u shared=%u cycles=%lu calls=%u values=%u fcsr=%lu vcsr=%lu max_abs=%08x pair_max_abs=%08x pair_bits_differ=%u errors=%u hex=",
        trial,order[trial],(unsigned long)elapsed,calls,values,(unsigned long)fc,(unsigned long)vc,
        bits(max_abs),bits(pair_max_abs),pair_bits_differ,errors);
    for(unsigned head=0;head<HEADS;++head)
      for(unsigned d=0;d<DIM;++d) printf("%08x",bits(output.data[head][d]));
    printf("\n");
    if(errors) return 1;
  }
  printf("QUANT_ATTN_SUITE_PASS trials=4 outputs=768 golden_tolerance=1 ordinary_repeats_exact=1\n");
  return 0;
}
