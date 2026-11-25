/* SDK softmax/store are compiled once and shared unchanged by all arms. */
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
  const size_t vl = __riscv_vsetvl_e16m2(p->descriptor.head_dim);
  for (unsigned t = 0; t < tokens; ++t) {
    const _Float16 *k = (const _Float16 *)(uintptr_t)(p->descriptor.k_base +
        (start+t)*p->descriptor.k_token_stride_bytes);
    __riscv_vsse16_v_f16m2(&packed.key[0][t], 128,
        __riscv_vle16_v_f16m2(k, vl), vl);
  }
}

extern void attention_memory_qk_panel4(const void *, float *, unsigned, size_t,
                                      unsigned, const void *);
extern void attention_memory_pv_rotation(const float *, void *, const float *,
                                         unsigned, unsigned, const void *, size_t);

__attribute__((noinline, noclone)) akv_status_t attention_rvv_group(
    const akv_attention_plan_t *p, akv_attention_v2_workspace_t *w) {
  if (!common_v2_plan_is_valid(p) || p->descriptor.q_rows != 2)
    return AKV_STATUS_BAD_ARGUMENT;
  const unsigned dim = p->descriptor.head_dim;
  initialize_workspace(w, 2, dim);
  for (unsigned start = 0; start < p->descriptor.kv_length; start += 64) {
    const unsigned tokens = akv_v2_tile_length(p->descriptor.kv_length, start);
    attention_rvv_pack(p, start, tokens);
    attention_memory_qk_panel4((const void *)(uintptr_t)p->descriptor.q_base,
        w->score[0], tokens, p->descriptor.q_row_stride_bytes, dim, packed.key);
    apply_scale_mask_and_softmax(p->mask, p->scale, w, start, tokens, 2, NULL, 0);
    attention_memory_pv_rotation(w->score[0], w->accumulator[0], w->old_scale,
        tokens, dim, (const void *)(uintptr_t)(p->descriptor.v_base +
        start*p->descriptor.v_token_stride_bytes), p->descriptor.v_token_stride_bytes);
  }
  store_outputs(p->output, p->output_row_stride_bytes, w, 2, dim);
  return AKV_STATUS_OK;
}
