/* One unchanged archived SDK C translation unit supplies native D256, online
 * softmax and final store. The comparator below uses ordinary memory only. */
#include "akv_v2_native_riscv.c"

static struct __attribute__((aligned(64))) {
  unsigned char before[64]; _Float16 key[256][64]; unsigned char after[64];
} packed;

void d256_memory_reset(void) { memset(&packed,0xa5,sizeof(packed)); }
int d256_memory_guards(void) {
  for (unsigned i=0;i<64;++i)
    if (packed.before[i]!=0xa5 || packed.after[i]!=0xa5) return 0;
  return 1;
}
__attribute__((noinline,noclone)) void d256_memory_pack(const akv_attention_plan_t *p) {
  for (unsigned t=0;t<17;++t)
    for (unsigned offset=0;offset<256;) {
      const size_t vl=__riscv_vsetvl_e16m2(256-offset);
      const _Float16 *k=(const _Float16 *)(uintptr_t)(p->descriptor.k_base+
          t*p->descriptor.k_token_stride_bytes)+offset;
      __riscv_vsse16_v_f16m2(&packed.key[offset][t],128,__riscv_vle16_v_f16m2(k,vl),vl);
      offset+=vl;
    }
}
__attribute__((noinline,noclone)) void d256_memory_qk(const akv_attention_plan_t *p,
    akv_attention_v2_workspace_t *w) {
  const size_t vl=__riscv_vsetvl_e16m1(17);
  const _Float16 *q0=(const _Float16 *)(uintptr_t)p->descriptor.q_base;
  const _Float16 *q1=(const _Float16 *)((const char *)q0+p->descriptor.q_row_stride_bytes);
  const _Float16 *q2=(const _Float16 *)((const char *)q1+p->descriptor.q_row_stride_bytes);
  const _Float16 *q3=(const _Float16 *)((const char *)q2+p->descriptor.q_row_stride_bytes);
  vfloat32m2_t s0=__riscv_vfmv_v_f_f32m2(0,vl),s1=s0,s2=s0,s3=s0;
  for (unsigned d=0;d<256;++d) {
    const vfloat16m1_t k=__riscv_vle16_v_f16m1(packed.key[d],vl);
    s0=__riscv_vfwmacc_vf_f32m2(s0,q0[d],k,vl);
    s1=__riscv_vfwmacc_vf_f32m2(s1,q1[d],k,vl);
    s2=__riscv_vfwmacc_vf_f32m2(s2,q2[d],k,vl);
    s3=__riscv_vfwmacc_vf_f32m2(s3,q3[d],k,vl);
  }
  __riscv_vse32_v_f32m2(w->score[0],s0,vl);__riscv_vse32_v_f32m2(w->score[1],s1,vl);
  __riscv_vse32_v_f32m2(w->score[2],s2,vl);__riscv_vse32_v_f32m2(w->score[3],s3,vl);
}
__attribute__((noinline,noclone)) void d256_memory_pv(const akv_attention_plan_t *p,
    akv_attention_v2_workspace_t *w,float token_scale[8][64]) {
  for (unsigned offset=0;offset<256;offset+=128) {
    const size_t vl=__riscv_vsetvl_e16m2(128);
    for (unsigned h=0;h<4;++h) {
      vfloat16m2_t acc=__riscv_vle16_v_f16m2((const _Float16 *)w->accumulator[h]+offset,vl);
      for (unsigned t=0;t<17;++t) {
        uint32_t scale,weight;
        memcpy(&scale,&token_scale[h][t],4);memcpy(&weight,&w->score[h][t],4);
        if (scale!=0x3f800000) {
          const vfloat32m4_t scaled=__riscv_vfmul_vf_f32m4(
              __riscv_vfwcvt_f_f_v_f32m4(acc,vl),token_scale[h][t],vl);
          acc=__riscv_vfncvt_f_f_w_f16m2(scaled,vl);
        }
        if (weight) {
          /* D256's value_descriptor K stream is V[0:128], not the score
           * descriptor's V stream, which is K[128:256]. */
          const _Float16 *v=(const _Float16 *)(uintptr_t)(p->value_descriptor.k_base+
              t*p->value_descriptor.k_token_stride_bytes)+offset;
          const vfloat32m4_t updated=__riscv_vfmacc_vf_f32m4(
              __riscv_vfwcvt_f_f_v_f32m4(acc,vl),w->score[h][t],
              __riscv_vfwcvt_f_f_v_f32m4(__riscv_vle16_v_f16m2(v,vl),vl),vl);
          acc=__riscv_vfncvt_f_f_w_f16m2(updated,vl);
        }
      }
      __riscv_vse16_v_f16m2((_Float16 *)w->accumulator[h]+offset,acc,vl);
    }
  }
}
__attribute__((noinline,noclone)) akv_status_t d256_memory_group(
    const akv_attention_plan_t *p,akv_attention_v2_workspace_t *w) {
  if (!akv_attention_plan_v2_is_valid(p) || p->d_segment_count!=2 || p->logical_head_dim!=256 ||
      p->descriptor.q_rows!=4 || p->descriptor.kv_length!=17) return AKV_STATUS_SHAPE;
  float token_scale[8][64];
  initialize_workspace(w,4,256);d256_memory_pack(p);d256_memory_qk(p,w);
  prepare_d256_online_softmax(p->mask,p->scale,w,token_scale,0,17,4,NULL);
  d256_memory_pv(p,w,token_scale);store_outputs(p->output,p->output_row_stride_bytes,w,4,256);
  return AKV_STATUS_OK;
}
