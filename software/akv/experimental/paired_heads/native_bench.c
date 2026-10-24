/* Benchmark-only translation unit. No production selector or kernel edits. */
#define akv_v2_compute_scores_f16_generic akv_bench_qk_f16_generic
#define akv_v2_update_outputs_f16_generic akv_bench_pv_f16_generic
#include "../../src/akv_v2_native_riscv.c"
#undef akv_v2_compute_scores_f16_generic
#undef akv_v2_update_outputs_f16_generic

#if AKV_REFILL_OVERLAP != 0
#error "Paired-head benchmark requires refill overlap OFF"
#endif
#if !defined(__riscv) || !defined(__riscv_vector) || !defined(__riscv_zvfh) || defined(SPIKE)
#error "This benchmark requires actual GNU RV64 vector/half native code"
#endif

extern void akv_v2_compute_scores_f16_generic(
    const uint16_t *, float *, uint32_t, size_t, uint32_t, uint32_t);
extern void akv_v2_update_outputs_f16_generic(
    const float *, uint16_t *, const float *, uint32_t, uint32_t, uint32_t);
extern void akv_experimental_qk_f16_pair_panel4(
    const uint16_t *, float *, uint32_t, size_t, uint32_t);
extern void akv_experimental_pv_f16_pair(
    const float *, uint16_t *, const float *, uint32_t, uint32_t);

/* Only the single-thread benchmark entry owns this state for a whole call. */
static unsigned bench_active;
static unsigned bench_pair_enabled;

void akv_bench_qk_f16_generic(const uint16_t *query, float *score,
    uint32_t tokens, size_t stride, uint32_t heads, uint32_t dim) {
  if (!bench_pair_enabled) {
    akv_v2_compute_scores_f16_generic(query, score, tokens, stride, heads, dim);
    return;
  }
  uint32_t head = 0;
  for (; head + 1 < heads; head += 2)
    akv_experimental_qk_f16_pair_panel4(
        (const uint16_t *)((const char *)query + head * stride),
        score + head * 64, tokens, stride, dim);
  if (head < heads)
    akv_v2_compute_scores_f16_generic(
        (const uint16_t *)((const char *)query + head * stride),
        score + head * 64, tokens, stride, 1, dim);
}

void akv_bench_pv_f16_generic(const float *score, uint16_t *accumulator,
    const float *old_scale, uint32_t tokens, uint32_t heads, uint32_t dim) {
  if (!bench_pair_enabled) {
    akv_v2_update_outputs_f16_generic(score, accumulator, old_scale, tokens, heads, dim);
    return;
  }
  uint32_t head = 0;
  for (; head + 1 < heads; head += 2)
    akv_experimental_pv_f16_pair(score + head * 64,
        accumulator + head * 256, old_scale + head, tokens, dim);
  if (head < heads)
    akv_v2_update_outputs_f16_generic(score + head * 64,
        accumulator + head * 256, old_scale + head, tokens, 1, dim);
}

static unsigned admit_pairs(const akv_attention_plan_t *plan, unsigned requested) {
  const uint32_t heads = plan->descriptor.q_rows;
  const uint32_t dim = plan->descriptor.head_dim;
  if (!requested || heads < 2 || heads > 8 ||
      (dim != 64 && dim != 96 && dim != 128) ||
      (heads == 6 && dim == 128)) return 0;
  akv_device_t device;
  if (akv_device_query(akv_native_info, NULL, &device) != AKV_STATUS_OK) return 0;
  const akv_capabilities_t *c = &device.capabilities;
  return c->valid && c->enabled && c->f16_payload && c->max_q_rows >= heads &&
         c->context_count && c->token_axis_valid && c->token_axis_enabled &&
         c->token_axis_tail && c->token_axis_row_view && c->token_axis_column_panel4 &&
         c->token_axis_tile_tokens == 64 &&
         (dim == 64 ? c->head_dim_64 : dim == 96 ? c->token_axis_d_axis_tail : c->head_dim_128);
}

akv_status_t akv_experimental_attention_pair_bench(
    const akv_attention_plan_t *plan, akv_attention_v2_workspace_t *workspace,
    unsigned requested, unsigned *effective) {
  if (effective == NULL || requested > 1 || bench_active ||
      !common_v2_plan_is_valid(plan)) return AKV_STATUS_BAD_ARGUMENT;
  *effective = 0;
  bench_active = 1;
  bench_pair_enabled = admit_pairs(plan, requested);
  *effective = bench_pair_enabled;
  const akv_status_t status = akv_attention_execute_v2_native(plan, workspace);
  bench_pair_enabled = 0;
  bench_active = 0;
  return status;
}
