/* Host-only tests of the actual core's preflight/leaf-dispatch helpers. */
#include "../../src/akv_v2_native_riscv.c"
#include <assert.h>
#include <fenv.h>
#include <stdio.h>

static _Alignas(64) uint16_t query[8][256], key[137][256], value[137][256], mask[137];
static _Alignas(64) float output[8][256];
static akv_device_t device;
static akv_attention_plan_t plan;
static akv_attention_v2_workspace_t workspace, saved_workspace;

static void make_plan(unsigned d, unsigned rows, unsigned tokens) {
  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);
  const akv_attention_problem_t problem = {
      .query = &query[0][0], .key = &key[0][0], .value = &value[0][0],
      .mask = mask, .output = &output[0][0], .q_row_stride_bytes = 512,
      .k_token_stride_bytes = 512, .v_token_stride_bytes = 512,
      .output_row_stride_bytes = 1024, .q_rows = rows, .head_dim = d,
      .kv_length = tokens, .scale = 0.125f};
  assert(akv_attention_plan_create_v2(&device, &problem, &plan) == AKV_STATUS_OK);
}

#if AKV_EXPERIMENTAL_RESIDENT_ATTENTION
static const akv_resident_attention_options_t admitted = {
    .requested = 1, .validated_available = 1, .platform_admitted = 1,
    .whole_call_owned = 1, .decode_head_rows = 1, .query_tokens = 1,
    .plain_scores = 1, .refill_overlap = 0, .vlenb = 128, .frm = 0, .vstart = 0};
static unsigned expected_tokens, expected_dim, expected_rows, qk_calls, pv_calls;
static unsigned maps_checked, leaves_checked;

void akv_experimental_resident_qk(float *score, uint32_t tokens,
    uint32_t heads, uint32_t dim, uint32_t base) {
  assert(base == 2 * qk_calls && base < expected_rows);
  assert(score == workspace.score[base]);
  assert(tokens == expected_tokens && dim == expected_dim);
  assert(heads == (expected_rows - base >= 2 ? 2u : 1u));
  ++qk_calls;
  ++leaves_checked;
}

void akv_experimental_resident_pv(const float *score, uint16_t *accum,
    const float *scale, uint32_t tokens, uint32_t dim, uint32_t heads) {
  const unsigned base = 2 * pv_calls;
  assert(qk_calls == (expected_rows + 1) / 2 && base < expected_rows);
  assert(score == workspace.score[base] && accum == workspace.accumulator[base]);
  assert(scale == &workspace.old_scale[base]);
  assert(tokens == expected_tokens && dim == expected_dim);
  assert(heads == (expected_rows - base >= 2 ? 2u : 1u));
  ++pv_calls;
  ++leaves_checked;
}

static void check_map(const akv_resident_attention_tile_t *tile, unsigned tokens) {
  expected_tokens = tokens;
  expected_dim = plan.descriptor.head_dim;
  expected_rows = plan.descriptor.q_rows;
  assert(tile->tokens == tokens && tile->head_dim == expected_dim);
  assert(tile->pair_count == (expected_rows + 1) / 2);
  for (unsigned i = 0; i < tile->pair_count; ++i) {
    const akv_resident_attention_pair_t *p = &tile->pairs[i];
    const unsigned heads = expected_rows - 2*i >= 2 ? 2 : 1;
    const unsigned code = expected_dim == 64 ? 0 : expected_dim == 96 ? 2 : 1;
    const uint64_t control = (tokens - 1) | ((heads - 1) << 6) | (code << 7);
    assert(p->query_base == 2*i && p->heads == heads);
    assert(p->pv_control == control && p->qk_control == (control | (uint64_t)(2*i) << 9));
  }
  qk_calls = pv_calls = 0;
  resident_qk_tile(tile, &workspace);
  resident_pv_tile(tile, &workspace);
  assert(qk_calls == tile->pair_count && pv_calls == tile->pair_count);
  ++maps_checked;
}

static void check_rejected(const akv_resident_attention_options_t *options,
                           const akv_attention_features_t *features,
                           unsigned actual_overlap) {
  resident_schedule_t schedule, saved;
  memset(&schedule, 0xa5, sizeof(schedule));
  memcpy(&saved, &schedule, sizeof(saved));
  assert(!prepare_resident_schedule(&device, &plan, options, features,
                                    actual_overlap, &schedule));
  assert(memcmp(&saved, &schedule, sizeof(saved)) == 0);
}

static void selection_and_dispatch(void) {
  const unsigned dims[] = {64, 96, 128};
  const unsigned lengths[] = {1, 64, 65, 137};
  for (unsigned d = 0; d < 3; ++d)
    for (unsigned rows = 1; rows <= 8; ++rows)
      for (unsigned t = 0; t < 4; ++t) {
        make_plan(dims[d], rows, lengths[t]);
        resident_schedule_t schedule;
        assert(prepare_resident_schedule(&device, &plan, &admitted, NULL, 0, &schedule));
        assert(schedule.full.tile_start == 0);
        assert(schedule.tail.tile_start == (lengths[t] - 1) / 64 * 64);
        check_map(&schedule.full, lengths[t] < 64 ? lengths[t] : 64);
        check_map(&schedule.tail, (lengths[t] - 1) % 64 + 1);
      }
  /* Distinct FULL groups restart the local H2/H1 bases, not global heads 0/3. */
  for (unsigned group = 0; group < 2; ++group) {
    make_plan(96, 3, 65);
    resident_schedule_t schedule;
    assert(prepare_resident_schedule(&device, &plan, &admitted, NULL, 0, &schedule));
    check_map(&schedule.full, 64);
    check_map(&schedule.tail, 1);
  }
  make_plan(128, 6, 137);
  check_rejected(NULL, NULL, 0);
  akv_resident_attention_options_t options = admitted;
#define REJECT(field, value) do { options = admitted; options.field = value; \
    check_rejected(&options, NULL, 0); } while (0)
  REJECT(requested, 0);
  REJECT(validated_available, 0);
  REJECT(platform_admitted, 0);
  REJECT(whole_call_owned, 0);
  REJECT(decode_head_rows, 0);
  REJECT(query_tokens, 2);
  REJECT(plain_scores, 0);
  REJECT(refill_overlap, 1);
  REJECT(vlenb, 64);
  REJECT(frm, 1);
  REJECT(vstart, 1);
#undef REJECT
  akv_attention_features_t features = {0};
  check_rejected(&admitted, &features, 0); /* Actual feature state beats claim. */
  assert(akv_refill_workspace_disjoint(&plan.descriptor, &workspace, sizeof(workspace)));
  check_rejected(&admitted, NULL, 1); /* Effective overlap beats caller's zero. */
  make_plan(256, 3, 65);
  check_rejected(&admitted, NULL, 0);
  make_plan(96, 3, 65);
  plan.descriptor.element_format = 2;
  check_rejected(&admitted, NULL, 0);
  make_plan(96, 3, 65);
  for (unsigned frm = 0; frm < 8; ++frm)
    assert(resident_state_matches(128, frm, 0) == (frm == 0));
  assert(!resident_state_matches(64, 0, 0));
  assert(!resident_state_matches(256, 0, 0));
  assert(!resident_state_matches(128, 0, 1));
  assert(!resident_state_matches(128, 0, UINTPTR_MAX));

  assert(akv_experimental_attention_execute_v2_native(&device, &plan, &workspace,
      NULL, &admitted, 2) == AKV_STATUS_BAD_ARGUMENT);
  assert(akv_experimental_attention_execute_v2_native(NULL, &plan, &workspace,
      NULL, &admitted, 1) == AKV_STATUS_BAD_ARGUMENT);
  assert(akv_experimental_attention_execute_v2_native(&device, &plan, &workspace,
      NULL, NULL, 1) == AKV_STATUS_BAD_ARGUMENT);
  for (unsigned automatic = 0; automatic <= 1; ++automatic) {
    options = admitted;
    options.platform_admitted = 0;
    assert(akv_experimental_attention_execute_v2_native(&device, &plan, &workspace,
        NULL, &options, automatic) == AKV_STATUS_RUNTIME_UNAVAILABLE);
    options = admitted;
    options.whole_call_owned = 0;
    assert(akv_experimental_attention_execute_v2_native(&device, &plan, &workspace,
        NULL, &options, automatic) == AKV_STATUS_RUNTIME_UNAVAILABLE);
    options = admitted;
    options.requested = 0;
    assert(akv_experimental_attention_execute_v2_native(&device, &plan, &workspace,
        NULL, &options, automatic) == AKV_STATUS_RUNTIME_UNAVAILABLE);
    options = admitted;
    options.validated_available = 0;
    assert(akv_experimental_attention_execute_v2_native(&device, &plan, &workspace,
        NULL, &options, automatic) == AKV_STATUS_RUNTIME_UNAVAILABLE);
  }
  printf("HOST_STUB_MAPS=%u LEAF_CALLS=%u numerical_execution=0\n", maps_checked, leaves_checked);
}
#endif

int main(void) {
  memset(&workspace, 0xa5, sizeof(workspace));
  memcpy(&saved_workspace, &workspace, sizeof(workspace));
  assert(fesetround(FE_DOWNWARD) == 0);
  assert(feraiseexcept(FE_INVALID | FE_INEXACT) == 0);
  const int flags = fetestexcept(FE_ALL_EXCEPT);
#if AKV_EXPERIMENTAL_RESIDENT_ATTENTION
  selection_and_dispatch();
#endif
  make_plan(128, 2, 137);
  assert(akv_attention_execute_v2_native(&plan, &workspace) == AKV_STATUS_RUNTIME_UNAVAILABLE);
  assert(akv_attention_execute_v2_native_auto(&device, &plan, &workspace) == AKV_STATUS_RUNTIME_UNAVAILABLE);
  assert(akv_attention_execute_v2_with_features_native(&plan, &workspace, NULL) == AKV_STATUS_RUNTIME_UNAVAILABLE);
  assert(akv_attention_execute_v2_with_features_native_auto(&device, &plan, &workspace, NULL) == AKV_STATUS_RUNTIME_UNAVAILABLE);
  assert(memcmp(&saved_workspace, &workspace, sizeof(workspace)) == 0);
  assert(fegetround() == FE_DOWNWARD && fetestexcept(FE_ALL_EXCEPT) == flags);
  assert(akv_resident_qk_is_supported() == 0 && akv_resident_pv_is_supported() == 0);
  assert(akv_resident_qk_capability_word(4, 1) == 0 && akv_resident_pv_capability_word(4, 1) == 0);
  printf("EXECUTOR_HOST_PASS macro=%d native_execution=0\n", AKV_EXPERIMENTAL_RESIDENT_ATTENTION);
  return 0;
}
