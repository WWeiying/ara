#include "software/akv/experimental/resident_attention/dispatch.h"
#include "software/akv/experimental/paired_heads/auto_policy.h"

#include <assert.h>
#include <fenv.h>
#include <stdio.h>
#include <string.h>

static struct __attribute__((aligned(64))) {
  uint16_t query[8][256];
  uint16_t key[137][256];
  uint16_t value[137][256];
  uint16_t mask[137];
  float output[8][256];
} payload, saved_payload;
static akv_device_t device;
static akv_attention_plan_t plan;
static unsigned schedules, pairs;

/* Deliberate host injection, NOT production discovery or acceptance evidence. */
static const akv_resident_attention_options_t enabled = {
    .requested = 1, .validated_available = 1, .platform_admitted = 1,
    .whole_call_owned = 1, .decode_head_rows = 1, .query_tokens = 1,
    .plain_scores = 1, .refill_overlap = 0, .vlenb = 128, .frm = 0, .vstart = 0};

static void make_plan(uint32_t dim, uint32_t rows, uint32_t context) {
  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);
  const size_t width = dim == 256 ? 256 : 128;
  const akv_attention_problem_t problem = {
      .query = &payload.query[0][0], .key = &payload.key[0][0],
      .value = &payload.value[0][0], .mask = payload.mask,
      .output = &payload.output[0][0], .q_row_stride_bytes = width * 2,
      .k_token_stride_bytes = width * 2, .v_token_stride_bytes = width * 2,
      .output_row_stride_bytes = width * 4, .q_rows = rows, .head_dim = dim,
      .kv_length = context, .scale = 0.125f};
  assert(akv_attention_plan_create_v2(&device, &problem, &plan) == AKV_STATUS_OK);
}

static akv_resident_attention_route_t select_route(
    const akv_resident_attention_options_t *options, unsigned started) {
  return akv_resident_attention_select(&device, &plan, options, started);
}

static uint64_t info_reader(void *context, unsigned index) {
  unsigned *seen = context;
  assert(index < 4); /* Existing device_query must not probe reserved index 4. */
  assert((*seen & (1u << index)) == 0);
  *seen |= 1u << index;
  return akv_capability_word(index, 1) | akv_v2_capability_word(index, 1);
}

static void test_default_and_fallback(void) {
  unsigned seen = 0;
  assert(akv_device_query(info_reader, &seen, &device) == AKV_STATUS_OK);
  assert(seen == 15);
  assert(akv_resident_qk_is_supported() == 0);
  assert(akv_resident_pv_is_supported() == 0);
  for (unsigned index = 0; index < 8; ++index) {
    assert(akv_resident_qk_capability_word(index, 1) == 0);
    assert(akv_resident_pv_capability_word(index, 1) == 0);
  }

  make_plan(96, 7, 137);
  const akv_resident_attention_options_t off = {0};
  assert(select_route(&off, 0) == AKV_RESIDENT_KEEP_NATIVE);
  assert(select_route(NULL, 0) == AKV_RESIDENT_KEEP_NATIVE);
  assert(akv_resident_attention_select(NULL, &plan, &enabled, 0) ==
         AKV_RESIDENT_KEEP_NATIVE);
  assert(akv_resident_attention_select(&device, NULL, &enabled, 0) ==
         AKV_RESIDENT_KEEP_NATIVE);
  assert(select_route(&enabled, 0) == AKV_RESIDENT_USE_SHARED);

#define REJECT_OPTION(field, value) do { \
    akv_resident_attention_options_t options = enabled; \
    options.field = (value); \
    assert(select_route(&options, 0) == AKV_RESIDENT_KEEP_NATIVE); \
  } while (0)
  REJECT_OPTION(requested, 0);
  REJECT_OPTION(requested, 2);
  REJECT_OPTION(validated_available, 0);
  REJECT_OPTION(validated_available, 2);
  REJECT_OPTION(platform_admitted, 0);
  REJECT_OPTION(whole_call_owned, 0);
  REJECT_OPTION(decode_head_rows, 0); /* Prefill even with a fitting descriptor. */
  REJECT_OPTION(query_tokens, 0);
  REJECT_OPTION(query_tokens, 2); /* Multiple tokens even if labeled Decode. */
  REJECT_OPTION(query_tokens, UINT32_MAX);
  REJECT_OPTION(plain_scores, 0);
  REJECT_OPTION(refill_overlap, 1);
  REJECT_OPTION(vlenb, 64);
  REJECT_OPTION(vlenb, 256);
  REJECT_OPTION(vstart, 1);
  for (unsigned frm = 1; frm <= 7; ++frm) REJECT_OPTION(frm, frm);
#undef REJECT_OPTION

#define REJECT_CAP(field, value) do { \
    const akv_device_t saved = device; \
    device.capabilities.field = (value); \
    assert(select_route(&enabled, 0) == AKV_RESIDENT_KEEP_NATIVE); \
    device = saved; \
  } while (0)
  REJECT_CAP(valid, 0);
  REJECT_CAP(enabled, 0);
  REJECT_CAP(f16_payload, 0);
  REJECT_CAP(context_count, 0);
  REJECT_CAP(max_q_rows, 6);
  REJECT_CAP(max_q_rows, 9);
  REJECT_CAP(token_axis_valid, 0);
  REJECT_CAP(token_axis_enabled, 0);
  REJECT_CAP(token_axis_tail, 0);
  REJECT_CAP(token_axis_row_view, 0);
  REJECT_CAP(token_axis_tile_tokens, 32);
  REJECT_CAP(token_axis_d_axis_tail, 0);
  make_plan(64, 3, 137);
  REJECT_CAP(head_dim_64, 0);
  make_plan(128, 3, 137);
  REJECT_CAP(head_dim_128, 0);
#undef REJECT_CAP

  /* Ordinary panel4 advertising is neither shared availability nor required
   * by this injected contract. The original auto policy still sees it. */
  device.capabilities.token_axis_column_panel4 = 0;
  assert(select_route(&enabled, 0) == AKV_RESIDENT_USE_SHARED);
  assert(select_route(&off, 0) == AKV_RESIDENT_KEEP_NATIVE);
  assert(!akv_pair_f16_auto_admitted(&plan.descriptor, &device, 128, 1));

  for (unsigned rows = 1; rows <= 8; ++rows) {
    make_plan(128, rows, 137);
    const int native_pair = akv_pair_f16_auto_admitted(
        &plan.descriptor, &device, 128, 1);
    assert(native_pair == (rows >= 2 && rows != 6));
    assert(select_route(&off, 0) == AKV_RESIDENT_KEEP_NATIVE);
    assert(native_pair == akv_pair_f16_auto_admitted(
        &plan.descriptor, &device, 128, 1));
    /* Explicit native options are not inputs to, or outputs of, this selector. */
  }

  for (unsigned started = 1; started <= 3; ++started) {
    assert(select_route(&enabled, started) == AKV_RESIDENT_NO_RETRY);
    assert(select_route(&off, started) == AKV_RESIDENT_NO_RETRY);
    assert(akv_resident_attention_select(NULL, NULL, NULL, started) ==
           AKV_RESIDENT_NO_RETRY);
  }
}

static void check_tile(uint32_t start, uint32_t tokens) {
  akv_resident_attention_tile_t tile;
  memset(&tile, 0xa5, sizeof(tile));
  assert(akv_resident_attention_dispatch_plan(
      AKV_RESIDENT_USE_SHARED, &plan.descriptor, start, &tile) == AKV_STATUS_OK);
  const uint32_t rows = plan.descriptor.q_rows;
  const uint32_t dim = plan.descriptor.head_dim;
  assert(tile.tile_start == start && tile.tokens == tokens && tile.head_dim == dim);
  assert(tile.pair_count == (rows + 1) / 2);
  unsigned visited = 0;
  for (unsigned i = 0; i < tile.pair_count; ++i) {
    const akv_resident_attention_pair_t *p = &tile.pairs[i];
    const unsigned base = i * 2, heads = rows - base >= 2 ? 2 : 1;
    /* Independent bit-layout oracle, not the SDK control constructors. */
    const unsigned dim_code = dim == 64 ? 0 : dim == 96 ? 2 : 1;
    const uint64_t low = (tokens - 1u) | ((heads - 1u) << 6) | (dim_code << 7);
    assert(p->query_base == base && p->heads == heads);
    assert(base + heads <= rows && base + heads <= 8);
    assert(p->pv_control == low);
    assert(p->qk_control == (low | ((uint64_t)base << 9)));
    assert(akv_resident_qk_command_is_valid(p->qk_control, 0, 0));
    assert(!akv_resident_qk_command_is_valid(p->qk_control, 0, 8));
    assert(akv_resident_pv_command_is_valid(p->pv_control, 0, 8));
    for (unsigned h = base; h < base + heads; ++h) {
      assert((visited & (1u << h)) == 0);
      visited |= 1u << h;
    }
    ++pairs;
  }
  assert(visited == (1u << rows) - 1u);
  for (unsigned i = tile.pair_count; i < 4; ++i) {
    assert(tile.pairs[i].heads == 0 && tile.pairs[i].query_base == 0);
    assert(tile.pairs[i].qk_control == 0 && tile.pairs[i].pv_control == 0);
  }
  ++schedules;
}

static void test_mapping(void) {
  const uint32_t dims[] = {64, 96, 128};
  for (unsigned d = 0; d < 3; ++d) {
    for (unsigned rows = 1; rows <= 8; ++rows) {
      for (unsigned tokens = 1; tokens <= 64; ++tokens) {
        make_plan(dims[d], rows, tokens);
        assert(select_route(&enabled, 0) == AKV_RESIDENT_USE_SHARED);
        check_tile(0, tokens);
      }
      make_plan(dims[d], rows, 137);
      check_tile(0, 64);
      check_tile(64, 64);
      check_tile(128, 9);
      assert(select_route(&enabled, 1) == AKV_RESIDENT_NO_RETRY);
    }
  }
  /* Seventeen heads split across three independently FULL-loaded local groups.
   * Global head offsets must never leak into querybase. Mapping has no cursor. */
  const unsigned groups[] = {8, 8, 1};
  for (unsigned group = 0; group < 3; ++group) {
    make_plan(96, groups[group], 137);
    check_tile(0, 64);
    check_tile(64, 64);
    check_tile(128, 9);
  }
}

static void expect_bad_map(akv_resident_attention_route_t route,
                           const akv_descriptor_t *descriptor,
                           uint32_t start) {
  akv_resident_attention_tile_t out, saved;
  memset(&out, 0xa5, sizeof(out));
  memcpy(&saved, &out, sizeof(out));
  assert(akv_resident_attention_dispatch_plan(route, descriptor, start, &out) !=
         AKV_STATUS_OK);
  assert(memcmp(&out, &saved, sizeof(out)) == 0);
}

static void test_invalid_and_purity(void) {
  make_plan(96, 7, 137);
  expect_bad_map(AKV_RESIDENT_KEEP_NATIVE, &plan.descriptor, 0);
  expect_bad_map(AKV_RESIDENT_NO_RETRY, &plan.descriptor, 0);
  expect_bad_map(AKV_RESIDENT_USE_SHARED, NULL, 0);
  assert(akv_resident_attention_dispatch_plan(
      AKV_RESIDENT_USE_SHARED, &plan.descriptor, 0, NULL) == AKV_STATUS_BAD_ARGUMENT);
  const uint32_t bad_start[] = {1, 63, 65, 136, 137, 192, UINT32_MAX};
  for (unsigned i = 0; i < sizeof(bad_start) / sizeof(bad_start[0]); ++i)
    expect_bad_map(AKV_RESIDENT_USE_SHARED, &plan.descriptor, bad_start[i]);

#define REJECT_DESCRIPTOR(field, value) do { \
    akv_attention_plan_t saved; \
    memcpy(&saved, &plan, sizeof(plan)); \
    plan.descriptor.field = (value); \
    assert(select_route(&enabled, 0) == AKV_RESIDENT_KEEP_NATIVE); \
    expect_bad_map(AKV_RESIDENT_USE_SHARED, &plan.descriptor, 0); \
    memcpy(&plan, &saved, sizeof(plan)); \
  } while (0)
  REJECT_DESCRIPTOR(element_format, 2); /* Non-F16 (including F32) excluded. */
  REJECT_DESCRIPTOR(q_rows, 0);
  REJECT_DESCRIPTOR(q_rows, 9); /* No truncation into three-bit querybase. */
  REJECT_DESCRIPTOR(head_dim, 32);
  REJECT_DESCRIPTOR(head_dim, 256);
  REJECT_DESCRIPTOR(kv_length, 0);
  REJECT_DESCRIPTOR(reserved0, 1);
  REJECT_DESCRIPTOR(q_base, UINT64_MAX - 31);
  REJECT_DESCRIPTOR(q_row_stride_bytes, 16);
#undef REJECT_DESCRIPTOR
  make_plan(256, 7, 137);
  assert(akv_attention_plan_v2_is_valid(&plan));
  assert(plan.descriptor.head_dim == 128); /* Physical shape alone is unsafe. */
  assert(select_route(&enabled, 0) == AKV_RESIDENT_KEEP_NATIVE);
  make_plan(96, 7, 137);
  plan.kernel_version = AKV_ATTENTION_KERNEL_VERSION_V1;
  assert(select_route(&enabled, 0) == AKV_RESIDENT_KEEP_NATIVE);
  make_plan(96, 7, 137);

  akv_attention_plan_t saved_plan;
  akv_device_t saved_device;
  akv_resident_attention_options_t options = enabled, saved_options;
  memcpy(&saved_plan, &plan, sizeof(plan));
  memcpy(&saved_device, &device, sizeof(device));
  memcpy(&saved_options, &options, sizeof(options));
  assert(fesetround(FE_DOWNWARD) == 0);
  assert(feraiseexcept(FE_INVALID | FE_INEXACT) == 0);
  const int flags = fetestexcept(FE_ALL_EXCEPT);
  /* Pure helpers consume the supplied snapshot, not host CSR/FP discovery. */
  assert(select_route(&options, 0) == AKV_RESIDENT_USE_SHARED);
  check_tile(128, 9);
  assert(fegetround() == FE_DOWNWARD && fetestexcept(FE_ALL_EXCEPT) == flags);
  assert(memcmp(&saved_plan, &plan, sizeof(plan)) == 0);
  assert(memcmp(&saved_device, &device, sizeof(device)) == 0);
  assert(memcmp(&saved_options, &options, sizeof(options)) == 0);
  assert(memcmp(&saved_payload, &payload, sizeof(payload)) == 0);
  assert(fesetround(FE_TONEAREST) == 0);
}

int main(void) {
  memset(&payload, 0xa5, sizeof(payload));
  memcpy(&saved_payload, &payload, sizeof(payload));
  test_default_and_fallback();
  test_mapping();
  test_invalid_and_purity();
  printf("RESIDENT_POLICY_HOST_PASS schedules=%u pairs=%u "
         "availability=injected production_capability=0 execution=none\n",
         schedules, pairs);
  return 0;
}
