/* Actual preflight/dispatch code, host leaves only; not target arithmetic. */
#if defined(AKV_FEATURES_V2_TARGET_GUARD)
#include "../experimental/resident_attention/features_v2/executor.h"
#include <stddef.h>

_Static_assert(AKV_STATUS_RUNTIME_UNAVAILABLE == 2, "Assembly status contract");
_Static_assert(offsetof(akv_resident_features_v2_options_t, requested) == 24,
               "Assembly requested offset");
static akv_resident_features_v2_options_t guard_options __attribute__((used)) = {
  .abi_version = AKV_RESIDENT_FEATURES_V2_ABI_VERSION,
  .struct_bytes = sizeof(akv_resident_features_v2_options_t),
  .score_policy = AKV_RESIDENT_FEATURES_V2_NATIVE_SCORE_ORDER,
  .row_meaning = AKV_RESIDENT_FEATURES_V2_DECODE_HEAD_ROWS,
  .query_tokens = 1, .feature_rows = 2, .requested = 1,
  .validated_available = 1, .platform_admitted = 1, .whole_call_owned = 1,
  .vlenb = 128,
};

/* Deliberate non-C-ABI entry: no compiler-generated C runs with vstart!=0.
 * Link the real core/dependencies, not host leaves. All other arguments point
 * outside Spike RAM. A trap or any snapshot/native fallback is a test failure.
 */
__asm__(
  ".section .text.init,\"ax\",@progbits\n.balign 4\n"
  ".global _start\n.type _start,@function\n_start:\n"
  "la sp, guard_stack_end\n"
  ".option push\n.option norelax\nla gp, __global_pointer$\n.option pop\n"
  "la t0, guard_fail\ncsrw mtvec, t0\n"
  "li t0, 0x6600\ncsrs mstatus, t0\ncsrwi fcsr, 0\n"
  "csrr t0, vlenb\nli t1, 128\nbne t0, t1, guard_fail\n"
  "la s0, guard_options\nli s1, 2\n"
  "guard_call:\n"
  "li a0, 0x40\nli a1, 0x80\nli a2, 0xc0\nli a3, 0x100\n"
  "mv a4, s0\nli a5, 0\ncsrwi vstart, 1\n"
  "call akv_experimental_attention_execute_features_v2_native\n"
  ".global guard_return\nguard_return:\n"
  "mv s2, a0\ncsrr s3, vstart\ncsrwi vstart, 0\n"
  "csrr t0, vstart\nbnez t0, guard_fail\n"
  "li t1, 2\nbne s2, t1, guard_fail\n"
  "li t1, 1\nbne s3, t1, guard_fail\n"
  "addi s1, s1, -1\nsw zero, 24(s0)\nbnez s1, guard_call\n"
  ".global guard_pass\nguard_pass:\nli t0, 1\nj guard_exit\n"
  ".balign 4\n.global guard_fail\nguard_fail:\ncsrwi vstart, 0\nli t0, 3\n"
  "guard_exit:\nla t1, tohost\nsd t0, 0(t1)\n1: j 1b\n"
  ".size _start, .-_start\n"
  ".section .bss\n.balign 16\nguard_stack:\n.skip 16384\nguard_stack_end:\n"
  ".section .tohost,\"aw\",@progbits\n.balign 64\n"
  ".global tohost\ntohost: .dword 0\n.global fromhost\nfromhost: .dword 0\n"
);
#else
#include "akv_v2_native_riscv.c"
#include <assert.h>
#include <fenv.h>
#include <float.h>
#include <math.h>
#include <stdio.h>

static _Alignas(64) uint16_t query[8][256], key[65535][256], value[65535][256], mask[65535];
static _Alignas(64) float output[8][256];
static akv_device_t device;
static akv_attention_plan_t plan;
static akv_attention_v2_workspace_t workspace, saved_workspace;
static unsigned maps, leaves, qk_calls, pv_calls, expected_tokens;

static const akv_resident_features_v2_options_t admitted = {
  .abi_version = AKV_RESIDENT_FEATURES_V2_ABI_VERSION,
  .struct_bytes = sizeof(akv_resident_features_v2_options_t),
  .score_policy = AKV_RESIDENT_FEATURES_V2_NATIVE_SCORE_ORDER,
  .row_meaning = AKV_RESIDENT_FEATURES_V2_DECODE_HEAD_ROWS,
  .query_tokens = 1, .feature_rows = 2, .requested = 1,
  .validated_available = 1, .platform_admitted = 1, .whole_call_owned = 1,
  .vlenb = 128, .frm = 0, .vstart = 0, .refill_overlap = 0,
};
static const akv_resident_attention_options_t old_admitted = {
  .requested = 1, .validated_available = 1, .platform_admitted = 1,
  .whole_call_owned = 1, .decode_head_rows = 1, .query_tokens = 1,
  .plain_scores = 1, .vlenb = 128,
};

static void make_plan(unsigned dim, unsigned rows, unsigned tokens) {
  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);
  const akv_attention_problem_t problem = {
    .query = query[0], .key = key[0], .value = value[0], .mask = mask,
    .output = output[0], .q_row_stride_bytes = 512, .k_token_stride_bytes = 512,
    .v_token_stride_bytes = 512, .output_row_stride_bytes = 1024,
    .q_rows = rows, .head_dim = dim, .kv_length = tokens, .scale = 0.125f,
  };
  assert(akv_attention_plan_create_v2(&device, &problem, &plan) == AKV_STATUS_OK);
}

static akv_attention_features_t features(unsigned flags) {
  akv_attention_features_t f = {0};
  f.softcap = flags & 1u ? 2.0f : 0.0f;
  f.mask_scale_enabled = !!(flags & 2u);
  f.position_bias_enabled = !!(flags & 4u);
  f.sinks_enabled = !!(flags & 8u);
  f.window_enabled = !!(flags & 16u);
  f.key_position_base = 1000;
  f.query_position = 1000 + plan.descriptor.kv_length - 1;
  f.window_left = 63;
  f.window_right = 1;
  for (unsigned h = 0; h < AKV_MAX_Q_ROWS; ++h) {
    f.mask_scale[h] = 1.0f + (float)h * 0.125f;
    f.position_slope[h] = (float)h * -0.125f;
    f.sinks[h] = (float)h - 2.0f;
  }
  return f;
}

void akv_experimental_resident_qk(float *score, uint32_t tokens,
    uint32_t heads, uint32_t dim, uint32_t base) {
  assert(base == 2*qk_calls && score == workspace.score[base]);
  assert(tokens == expected_tokens && dim == plan.descriptor.head_dim);
  assert(heads == (plan.descriptor.q_rows-base >= 2 ? 2u : 1u));
  ++qk_calls;
  ++leaves;
}

void akv_experimental_resident_pv(const float *score, uint16_t *accumulator,
    const float *scale, uint32_t tokens, uint32_t dim, uint32_t heads) {
  const unsigned base = 2*pv_calls;
  assert(qk_calls == (plan.descriptor.q_rows+1u)/2u);
  assert(score == workspace.score[base] && accumulator == workspace.accumulator[base]);
  assert(scale == &workspace.old_scale[base]);
  assert(tokens == expected_tokens && dim == plan.descriptor.head_dim);
  assert(heads == (plan.descriptor.q_rows-base >= 2 ? 2u : 1u));
  ++pv_calls;
  ++leaves;
}

static void check_map(const akv_resident_attention_tile_t *tile, unsigned tokens) {
  assert(tile->tokens == tokens && tile->head_dim == plan.descriptor.head_dim);
  assert(tile->pair_count == (plan.descriptor.q_rows+1u)/2u);
  for (unsigned i = 0; i < tile->pair_count; ++i) {
    const unsigned heads = plan.descriptor.q_rows-2*i >= 2 ? 2 : 1;
    const unsigned code = tile->head_dim == 64 ? 0 : tile->head_dim == 96 ? 2 : 1;
    const uint64_t pv = (tokens-1) | ((heads-1)<<6) | (code<<7);
    assert(tile->pairs[i].query_base == 2*i && tile->pairs[i].heads == heads);
    assert(tile->pairs[i].pv_control == pv && tile->pairs[i].qk_control == (pv | (uint64_t)(2*i)<<9));
  }
  expected_tokens = tokens;
  qk_calls = pv_calls = 0;
  resident_qk_tile(tile, &workspace);
  resident_pv_tile(tile, &workspace);
  assert(pv_calls == tile->pair_count);
  ++maps;
}

static void reject(const akv_resident_features_v2_options_t *o,
                   const akv_attention_features_t *f, unsigned overlap) {
  resident_schedule_t schedule, before;
  memset(&schedule, 0xa5, sizeof(schedule));
  before = schedule;
  assert(!prepare_resident_features_v2_schedule(&device, &plan, o, f, overlap, &schedule));
  assert(memcmp(&before, &schedule, sizeof(schedule)) == 0);
}

static void selection(void) {
  const unsigned dimensions[] = {64, 96, 128};
  const unsigned lengths[] = {1, 2, 63, 64, 65, 129, 137, 257, 4097, 65535};
  for (unsigned d = 0; d < 3; ++d)
    for (unsigned rows = 1; rows <= 8; ++rows)
      for (unsigned t = 0; t < 10; ++t) {
        make_plan(dimensions[d], rows, lengths[t]);
        akv_resident_features_v2_options_t o = admitted;
        o.feature_rows = rows;
        for (unsigned bits = 0; bits < 32; ++bits) {
          akv_attention_features_t f = features(bits), saved = f;
          resident_schedule_t schedule;
          assert(prepare_resident_features_v2_schedule(&device, &plan, &o, &f, 0, &schedule));
          assert(!prepare_resident_schedule(&device, &plan, &old_admitted, &f, 0, &schedule));
          assert(memcmp(&saved, &f, sizeof(f)) == 0);
          check_map(&schedule.full, lengths[t] < 64 ? lengths[t] : 64);
          check_map(&schedule.tail, (lengths[t]-1)%64+1);
          assert(schedule.tail.tile_start == (lengths[t]-1)/64*64);
        }
      }
  make_plan(128, 2, 137);
  akv_attention_features_t f = features(31);
  akv_resident_features_v2_options_t o;
#define REJECT(field, value) do { o = admitted; o.field = (value); reject(&o, &f, 0); } while (0)
  REJECT(abi_version, 0); REJECT(abi_version, 3); REJECT(struct_bytes, 0);
  REJECT(struct_bytes, sizeof(o)+8); REJECT(score_policy, 0); REJECT(score_policy, 2);
  REJECT(row_meaning, 0); REJECT(row_meaning, 2); REJECT(query_tokens, 0); REJECT(query_tokens, 2);
  REJECT(feature_rows, 1); REJECT(feature_rows, 9); REJECT(requested, 0); REJECT(requested, 2);
  REJECT(validated_available, 0); REJECT(platform_admitted, 0); REJECT(whole_call_owned, 0);
  REJECT(refill_overlap, 1); REJECT(vlenb, 64); REJECT(vlenb, 256); REJECT(vstart, 1);
  for (unsigned rm = 1; rm < 8; ++rm) REJECT(frm, rm);
#undef REJECT
  reject(NULL, &f, 0);
  reject(&admitted, &f, 1);
  assert(akv_resident_features_v2_select(NULL, NULL, NULL, NULL, 1) == AKV_RESIDENT_NO_RETRY);
  assert(akv_resident_features_v2_select(NULL, &plan, &f, &admitted, 0) == AKV_RESIDENT_KEEP_NATIVE);
  const akv_device_t saved = device;
#define CAP(field, value) do { device = saved; device.capabilities.field = (value); reject(&admitted, &f, 0); } while (0)
  CAP(valid, 0); CAP(enabled, 0); CAP(f16_payload, 0); CAP(context_count, 0);
  CAP(max_q_rows, 1); CAP(max_q_rows, 9); CAP(token_axis_valid, 0); CAP(token_axis_enabled, 0);
  CAP(token_axis_tail, 0); CAP(token_axis_row_view, 0); CAP(token_axis_tile_tokens, 32);
  CAP(head_dim_128, 0);
#undef CAP
  device = saved;
  make_plan(256, 2, 137);
  reject(&admitted, &f, 0);
  make_plan(128, 2, 137);
  plan.descriptor.element_format = 2;
  reject(&admitted, &f, 0);
}

static float bits_float(uint32_t bits) {
  float result;
  memcpy(&result, &bits, sizeof(result));
  return result;
}

static void feature_contract(void) {
  make_plan(128, 2, 137);
  const akv_attention_features_t good = features(31);
  akv_attention_features_t f = good;
#define BAD(field, value) do { f = good; f.field = (value); \
    assert(akv_resident_features_v2_contract(&plan, &f, &admitted) == AKV_STATUS_BAD_ARGUMENT); \
    reject(&admitted, &f, 0); } while (0)
  BAD(softcap, -1.0f); BAD(softcap, bits_float(0x7f800001));
  BAD(mask_scale_enabled, 2); BAD(position_bias_enabled, 2); BAD(sinks_enabled, 2); BAD(window_enabled, 2);
  BAD(mask_scale[1], 0.0f); BAD(mask_scale[1], bits_float(0x7f800001));
  BAD(position_slope[1], INFINITY); BAD(sinks[1], bits_float(0x7f800001));
  BAD(key_position_base, UINT64_MAX-135);
#undef BAD
  f = good;
  f.key_position_base = UINT64_MAX-136;
  f.query_position = UINT64_MAX;
  assert(akv_resident_features_v2_contract(&plan, &f, &admitted) == AKV_STATUS_OK);
  f.sinks[7] = bits_float(0x7f800001); /* Unused local row must not be consumed. */
  assert(akv_resident_features_v2_contract(&plan, &f, &admitted) == AKV_STATUS_OK);
  assert(akv_resident_features_v2_contract(&plan, NULL, &admitted) == AKV_STATUS_OK);

  akv_attention_features_t zero = {0};
  assert(akv_attention_can_use_plain_scores(&zero, mask, 137));
  mask[64] = 0xfc00;
  assert(!akv_attention_can_use_plain_scores(&zero, mask, 137));
  mask[64] = 0x3800;
  assert(!akv_attention_can_use_plain_scores(&zero, mask, 137));
  mask[64] = 0;
}

static void entry_rejections(void) {
  make_plan(128, 2, 137);
  akv_attention_features_t f = features(31);
  akv_resident_features_v2_options_t o = admitted;
  _Alignas(64) unsigned char raw_plan[sizeof(plan)+64];
  memcpy(raw_plan+1, &plan, sizeof(plan));
  const akv_attention_plan_t *misaligned = (const akv_attention_plan_t *)(const void *)(raw_plan+1);
  assert(akv_resident_features_v2_contract(misaligned, &f, &o) == AKV_STATUS_BAD_ARGUMENT);
  assert(akv_resident_features_v2_select(&device, misaligned, &f, &o, 0) == AKV_RESIDENT_KEEP_NATIVE);
  assert(akv_experimental_attention_execute_features_v2_native(&device, misaligned,
      &workspace, &f, &o, 0) == AKV_STATUS_BAD_ARGUMENT);
#define ENTRY(dev, opt, policy) akv_experimental_attention_execute_features_v2_native( \
    dev, &plan, &workspace, &f, opt, policy)
  assert(ENTRY(NULL, &o, 0) == AKV_STATUS_BAD_ARGUMENT);
  assert(ENTRY(&device, NULL, 0) == AKV_STATUS_BAD_ARGUMENT);
  assert(ENTRY(&device, &o, 2) == AKV_STATUS_BAD_ARGUMENT);
  o.abi_version = 3;
  assert(ENTRY(&device, &o, 0) == AKV_STATUS_BAD_ARGUMENT);
  o = admitted; o.feature_rows = 1;
  assert(ENTRY(&device, &o, 0) == AKV_STATUS_BAD_ARGUMENT);
  o = admitted; o.query_tokens = 2;
  assert(ENTRY(&device, &o, 0) == AKV_STATUS_RUNTIME_UNAVAILABLE);
  for (unsigned automatic = 0; automatic < 2; ++automatic) {
    o = admitted;
    assert(ENTRY(&device, &o, automatic) == AKV_STATUS_RUNTIME_UNAVAILABLE); /* Host only. */
    o.requested = 0;
    assert(ENTRY(&device, &o, automatic) == AKV_STATUS_RUNTIME_UNAVAILABLE);
    o = admitted; o.platform_admitted = 0;
    assert(ENTRY(&device, &o, automatic) == AKV_STATUS_RUNTIME_UNAVAILABLE);
    o = admitted; o.whole_call_owned = 0;
    assert(ENTRY(&device, &o, automatic) == AKV_STATUS_RUNTIME_UNAVAILABLE);
  }
#undef ENTRY
}

static void software_feature_order(void) {
  /* Independent exact cases for the unchanged scalar transform, not libm equivalence. */
  make_plan(64, 2, 137);
  for (unsigned group = 0; group < 2; ++group) {
    akv_attention_features_t f = {0};
    f.mask_scale_enabled = f.position_bias_enabled = 1;
    f.key_position_base = 1000; f.query_position = 1063;
    for (unsigned h = 0; h < 2; ++h) {
      const unsigned global = group*2+h;
      f.mask_scale[h] = (float)(global+1);
      f.position_slope[h] = (float)(global+1)*0.25f;
      const float actual = akv_attention_score_transform(2.0f, 0.5f, 0x3800, h, 65, &f);
      assert(actual == 2.0f+(float)global);
    }
    resident_schedule_t schedule;
    assert(prepare_resident_features_v2_schedule(&device, &plan, &admitted, &f, 0, &schedule));
    assert(schedule.full.pairs[0].query_base == 0 && f.query_position == 1063);
    f.window_enabled = 1; f.window_left = f.window_right = 2;
    assert(isfinite(akv_attention_score_transform(2, 0.5f, 0, 0, 61, &f)));
    assert(isfinite(akv_attention_score_transform(2, 0.5f, 0, 0, 65, &f)));
    assert(akv_attention_score_transform(2, 0.5f, 0, 0, 60, &f) == -INFINITY);
    assert(akv_attention_score_transform(2, 0.5f, 0, 0, 66, &f) == -INFINITY);
  }
  assert(feclearexcept(FE_ALL_EXCEPT) == 0);
  assert(akv_attention_score_transform(FLT_MAX, FLT_MAX, 0xfc00, 0, 0, NULL) == -INFINITY);
  assert(fetestexcept(FE_ALL_EXCEPT) == 0); /* Mask return precedes multiplication. */
  akv_attention_features_t excluded = {0};
  excluded.window_enabled = excluded.position_bias_enabled = excluded.mask_scale_enabled = 1;
  excluded.key_position_base = 1000; excluded.query_position = 1063;
  excluded.softcap = 0x1p-149f;
  excluded.position_slope[0] = excluded.mask_scale[0] = FLT_MAX;
  assert(akv_attention_score_transform(2, 0.5f, 0x7bff, 0, 0, &excluded) == -INFINITY);
  assert(fetestexcept(FE_ALL_EXCEPT) == 0); /* Window skips all three later transforms. */
  assert(akv_attention_score_transform(FLT_MAX, FLT_MAX, 0x7bff, 0, 0, &excluded) == -INFINITY);
  assert(fetestexcept(FE_ALL_EXCEPT) == (FE_OVERFLOW | FE_INEXACT));
  assert(feclearexcept(FE_ALL_EXCEPT) == 0);
}

int main(void) {
  memset(&workspace, 0xa5, sizeof(workspace));
  saved_workspace = workspace;
  assert(fesetround(FE_DOWNWARD) == 0);
  assert(feraiseexcept(FE_INVALID | FE_INEXACT) == 0);
  const int before_flags = fetestexcept(FE_ALL_EXCEPT);
  selection(); feature_contract(); entry_rejections();
  assert(memcmp(&workspace, &saved_workspace, sizeof(workspace)) == 0);
  assert(fegetround() == FE_DOWNWARD && fetestexcept(FE_ALL_EXCEPT) == before_flags);
  assert(fesetround(FE_TONEAREST) == 0);
  software_feature_order();
  assert(akv_resident_qk_is_supported() == 0 && akv_resident_pv_is_supported() == 0);
  assert(akv_resident_qk_capability_word(4, 1) == 0 && akv_resident_pv_capability_word(4, 1) == 0);
  printf("FEATURES_V2_HOST_PASS maps=%u leaf_stubs=%u feature_combinations=32 native_execution=0\n", maps, leaves);
  return 0;
}
#endif
