/* Compile the archived SDK exactly once; share its unchanged softmax/store
 * implementation with this test-side memory-RVV baseline. */
#include "akv_v2_native_riscv.c"

static struct __attribute__((aligned(64))) {
  unsigned char before[64];
  _Float16 key[128][64];
  unsigned char after[64];
} packed;

void attention_rvv_reset(void) { memset(&packed, 0xa5, sizeof(packed)); }
int attention_rvv_guards(void) {
  for (unsigned i = 0; i < 64; ++i)
    if (packed.before[i] != 0xa5 || packed.after[i] != 0xa5) return 0;
  return 1;
}

__attribute__((noinline, noclone)) void attention_rvv_pack(
    const akv_attention_plan_t *p, unsigned start, unsigned tokens) {
  const unsigned dim = p->descriptor.head_dim;
  const size_t vl = __riscv_vsetvl_e16m2(dim);
  for (unsigned t = 0; t < tokens; ++t) {
    const _Float16 *k = (const _Float16 *)(uintptr_t)(p->descriptor.k_base +
        (start+t)*p->descriptor.k_token_stride_bytes);
    const vfloat16m2_t v = __riscv_vle16_v_f16m2(k, vl);
    __riscv_vsse16_v_f16m2(&packed.key[0][t], 128, v, vl);
  }
}

/* Two independent sequential-dimension F32 accumulators reuse each K load.
 * PV likewise shares V loads; neither loop changes the mathematical order. */
__attribute__((noinline, noclone)) void attention_rvv_qk_pair(
    const akv_attention_plan_t *p, akv_attention_v2_workspace_t *w,
    unsigned base, unsigned heads, unsigned tokens) {
  const unsigned dim = p->descriptor.head_dim;
  const size_t vl = __riscv_vsetvl_e16m1(tokens);
  const _Float16 *q0 = (const _Float16 *)(uintptr_t)(p->descriptor.q_base +
      base*p->descriptor.q_row_stride_bytes);
  const _Float16 *q1 = (const _Float16 *)((const char *)q0+p->descriptor.q_row_stride_bytes);
  vfloat32m2_t s0 = __riscv_vfmv_v_f_f32m2(0.0f, vl);
  vfloat32m2_t s1 = __riscv_vfmv_v_f_f32m2(0.0f, vl);
  for (unsigned d = 0; d < dim; ++d) {
    const vfloat16m1_t k = __riscv_vle16_v_f16m1(packed.key[d], vl);
    s0 = __riscv_vfwmacc_vf_f32m2(s0, q0[d], k, vl);
    if (heads == 2) s1 = __riscv_vfwmacc_vf_f32m2(s1, q1[d], k, vl);
  }
  __riscv_vse32_v_f32m2(w->score[base], s0, vl);
  if (heads == 2) __riscv_vse32_v_f32m2(w->score[base+1], s1, vl);
}

__attribute__((noinline, noclone)) void attention_rvv_pv_pair(
    const akv_attention_plan_t *p, akv_attention_v2_workspace_t *w,
    unsigned base, unsigned heads, unsigned start, unsigned tokens) {
  const size_t vl = __riscv_vsetvl_e16m2(p->descriptor.head_dim);
  vfloat16m2_t a0 = __riscv_vfmul_vf_f16m2(
      __riscv_vle16_v_f16m2((const _Float16 *)w->accumulator[base], vl),
      (_Float16)w->old_scale[base], vl);
  vfloat16m2_t a1 = __riscv_vfmv_v_f_f16m2(0.0f, vl);
  if (heads == 2) a1 = __riscv_vfmul_vf_f16m2(
      __riscv_vle16_v_f16m2((const _Float16 *)w->accumulator[base+1], vl),
      (_Float16)w->old_scale[base+1], vl);
  for (unsigned t = 0; t < tokens; ++t) {
    const _Float16 *v = (const _Float16 *)(uintptr_t)(p->descriptor.v_base +
        (start+t)*p->descriptor.v_token_stride_bytes);
    const vfloat16m2_t value = __riscv_vle16_v_f16m2(v, vl);
    a0 = __riscv_vfmacc_vf_f16m2(a0, (_Float16)w->score[base][t], value, vl);
    if (heads == 2) a1 = __riscv_vfmacc_vf_f16m2(
        a1, (_Float16)w->score[base+1][t], value, vl);
  }
  __riscv_vse16_v_f16m2((_Float16 *)w->accumulator[base], a0, vl);
  if (heads == 2) __riscv_vse16_v_f16m2((_Float16 *)w->accumulator[base+1], a1, vl);
}

__attribute__((noinline, noclone)) akv_status_t attention_rvv_group(
    const akv_attention_plan_t *p, akv_attention_v2_workspace_t *w) {
  if (!common_v2_plan_is_valid(p)) return AKV_STATUS_BAD_ARGUMENT;
  const unsigned rows = p->descriptor.q_rows, dim = p->descriptor.head_dim;
  initialize_workspace(w, rows, dim);
  for (unsigned start = 0; start < p->descriptor.kv_length; start += 64) {
    const unsigned tokens = akv_v2_tile_length(p->descriptor.kv_length, start);
    attention_rvv_pack(p, start, tokens);
    for (unsigned base = 0; base < rows; base += 2)
      attention_rvv_qk_pair(p, w, base, rows-base >= 2 ? 2 : 1, tokens);
    apply_scale_mask_and_softmax(p->mask, p->scale, w, start, tokens, rows, NULL, 0);
    for (unsigned base = 0; base < rows; base += 2)
      attention_rvv_pv_pair(p, w, base, rows-base >= 2 ? 2 : 1, start, tokens);
  }
  store_outputs(p->output, p->output_row_stride_bytes, w, rows, dim);
  return AKV_STATUS_OK;
}
