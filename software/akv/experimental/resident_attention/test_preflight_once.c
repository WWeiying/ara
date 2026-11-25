/* Differential preflight test: no custom instructions or payload accesses. */
#include "../../include/akv/akv.h"
#include <assert.h>
#include <fenv.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

static unsigned plan_checks, descriptor_checks;
static int counted_plan(const akv_attention_plan_t *p) {
  ++plan_checks;
  return akv_attention_plan_v2_is_valid(p);
}
static int counted_descriptor(const void *p) {
  ++descriptor_checks;
  return akv_v2_descriptor_is_valid(p);
}
#define akv_attention_plan_v2_is_valid counted_plan
#define akv_v2_descriptor_is_valid counted_descriptor
#include RESIDENT_CORE
#undef akv_attention_plan_v2_is_valid
#undef akv_v2_descriptor_is_valid

/* Linking only; preflight must never invoke a leaf. */
void akv_experimental_resident_qk_prepared(float *p, uint32_t n,
    uint32_t h, uint64_t c) {
  (void)p; (void)n; (void)h; (void)c; assert(0);
}
void akv_experimental_resident_pv_prepared(const float *p, uint16_t *a,
    const float *s, uint32_t n, uint32_t d, uint32_t h, uint64_t c) {
  (void)p; (void)a; (void)s; (void)n; (void)d; (void)h; (void)c; assert(0);
}

static akv_device_t device;
static akv_attention_plan_t plan;
static akv_resident_attention_options_t options;
static unsigned cases, accepted, descriptors, validators;
static unsigned feature_cases, feature_accepted;
static unsigned sample_descriptors, sample_validators;
static uint64_t digest = UINT64_C(14695981039346656037);

static void hash(const void *p, size_t n) {
  const unsigned char *b = p;
  for (size_t i = 0; i < n; ++i) {
    digest ^= b[i]; digest *= UINT64_C(1099511628211);
  }
}

static void fixture(unsigned d, unsigned rows, uint32_t tokens) {
  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);
  /* Fixed synthetic addresses are checked for overflow, never dereferenced. */
  const akv_attention_problem_t problem = {
    .query = (const uint16_t *)0x10000000, .key = (const uint16_t *)0x20000000,
    .value = (const uint16_t *)0x40000000, .mask = (const uint16_t *)0x60000000,
    .output = (float *)0x80000000, .q_row_stride_bytes = 512,
    .k_token_stride_bytes = 512, .v_token_stride_bytes = 512,
    .output_row_stride_bytes = 1024, .q_rows = rows, .head_dim = d,
    .kv_length = tokens, .scale = 0.125f};
  assert(akv_attention_plan_create_v2(&device, &problem, &plan) == AKV_STATUS_OK);
  options = (akv_resident_attention_options_t){
    .requested = 1, .validated_available = 1, .platform_admitted = 1,
    .whole_call_owned = 1, .decode_head_rows = 1, .query_tokens = 1,
    .plain_scores = 1, .vlenb = 128};
}

static void check(unsigned overlap, int missing_options, int missing_device,
                  int has_features) {
  resident_schedule_t schedule, saved;
  memset(&schedule, 0xa5, sizeof(schedule)); saved = schedule;
  akv_attention_features_t features = {0};
  const akv_resident_attention_options_t *o = missing_options ? NULL : &options;
  const akv_device_t *dev = missing_device ? NULL : &device;
  feclearexcept(FE_ALL_EXCEPT);
  feraiseexcept(FE_INEXACT);
  plan_checks = descriptor_checks = 0;
  /* Reproduce the production ordering, including the common entry check. */
  int valid = common_v2_plan_is_valid(&plan);
  int selected = valid && prepare_resident_schedule(dev, &plan, o,
      has_features ? &features : NULL, overlap, &schedule);
  unsigned dc = descriptor_checks, pc = plan_checks;
  int flags = fetestexcept(FE_ALL_EXCEPT);
  if (selected) {
    ++accepted; descriptors += dc; validators += pc;
    sample_descriptors = dc; sample_validators = pc;
    akv_resident_attention_tile_t full, tail;
    assert(akv_resident_attention_dispatch_plan(AKV_RESIDENT_USE_SHARED,
        &plan.descriptor, 0, &full) == AKV_STATUS_OK);
    assert(akv_resident_attention_dispatch_plan(AKV_RESIDENT_USE_SHARED,
        &plan.descriptor, schedule.tail.tile_start, &tail) == AKV_STATUS_OK);
    assert(memcmp(&schedule.full, &full, sizeof(full)) == 0);
    assert(memcmp(&schedule.tail, &tail, sizeof(tail)) == 0);
  } else assert(memcmp(&saved, &schedule, sizeof(saved)) == 0);
  hash(&valid, sizeof(valid)); hash(&selected, sizeof(selected));
  hash(&flags, sizeof(flags)); hash(&schedule, sizeof(schedule));
  /* Standalone APIs must retain their original validation and no-retry rules. */
  for (unsigned started = 0; started < 2; ++started) {
    int route = akv_resident_attention_select(dev, &plan, o, started);
    hash(&route, sizeof(route));
  }
  const uint32_t starts[] = {0, 1, 64, 128, UINT32_MAX - 63, UINT32_MAX};
  for (unsigned i = 0; i < sizeof(starts)/sizeof(starts[0]); ++i) {
    akv_resident_attention_tile_t tile;
    memset(&tile, 0xa5, sizeof(tile));
    int status = akv_resident_attention_dispatch_plan(AKV_RESIDENT_USE_SHARED,
        &plan.descriptor, starts[i], &tile);
    hash(&status, sizeof(status)); hash(&tile, sizeof(tile));
  }
  ++cases;
}

static void check_features(unsigned bits) {
  akv_attention_features_t f = {0};
  f.softcap = bits & 1u ? 2.0f : 0.0f;
  f.mask_scale_enabled = !!(bits & 2u);
  f.position_bias_enabled = !!(bits & 4u);
  f.sinks_enabled = !!(bits & 8u);
  f.window_enabled = !!(bits & 16u);
  f.key_position_base = 1000;
  f.query_position = 1000 + plan.descriptor.kv_length - 1;
  f.window_left = 63; f.window_right = 1;
  for (unsigned i = 0; i < AKV_MAX_Q_ROWS; ++i) {
    f.mask_scale[i] = 1.0f; f.position_slope[i] = -0.125f; f.sinks[i] = -2.0f;
  }
  const akv_resident_features_v2_options_t o = {
    .abi_version = AKV_RESIDENT_FEATURES_V2_ABI_VERSION, .struct_bytes = sizeof(o),
    .score_policy = AKV_RESIDENT_FEATURES_V2_NATIVE_SCORE_ORDER,
    .row_meaning = AKV_RESIDENT_FEATURES_V2_DECODE_HEAD_ROWS,
    .query_tokens = 1, .feature_rows = plan.descriptor.q_rows, .requested = 1,
    .validated_available = 1, .platform_admitted = 1, .whole_call_owned = 1,
    .vlenb = 128};
  resident_schedule_t schedule, saved;
  memset(&schedule, 0xa5, sizeof(schedule)); saved = schedule;
  int selected = prepare_resident_features_v2_schedule(&device, &plan, &o, &f, 0, &schedule);
  assert(selected);
  akv_resident_attention_tile_t full, tail;
  assert(akv_resident_attention_dispatch_plan(AKV_RESIDENT_USE_SHARED,
      &plan.descriptor, 0, &full) == AKV_STATUS_OK);
  assert(akv_resident_attention_dispatch_plan(AKV_RESIDENT_USE_SHARED,
      &plan.descriptor, schedule.tail.tile_start, &tail) == AKV_STATUS_OK);
  assert(memcmp(&full, &schedule.full, sizeof(full)) == 0);
  assert(memcmp(&tail, &schedule.tail, sizeof(tail)) == 0);
  hash(&selected, sizeof(selected)); hash(&schedule, sizeof(schedule));
  ++feature_accepted; ++feature_cases;
  schedule = saved;
  selected = prepare_resident_features_v2_schedule(&device, &plan, &o, &f, 1, &schedule);
  assert(!selected && memcmp(&saved, &schedule, sizeof(saved)) == 0);
  hash(&selected, sizeof(selected)); hash(&schedule, sizeof(schedule));
  ++feature_cases;
}

int main(void) {
  const unsigned dims[] = {64, 96, 128};
  const uint32_t lengths[] = {1, 2, 31, 63, 64, 65, 128, 137, 256, 257, 65535};
  for (unsigned d = 0; d < 3; ++d)
    for (unsigned h = 1; h <= 8; ++h)
      for (unsigned t = 0; t < sizeof(lengths)/sizeof(lengths[0]); ++t) {
        fixture(dims[d], h, lengths[t]); check(0, 0, 0, 0);
        for (unsigned f = 0; f < 32; ++f) check_features(f);
      }
  /* Exhaustively flip each bit of all input objects, not just happy shapes. */
  const size_t sizes[] = {sizeof(plan), sizeof(options), sizeof(device)};
  for (unsigned which = 0; which < 3; ++which)
    for (size_t byte = 0; byte < sizes[which]; ++byte)
      for (unsigned bit = 0; bit < 8; ++bit) {
        fixture(128, 3, 137);
        unsigned char *p = which == 0 ? (unsigned char *)&plan :
                           which == 1 ? (unsigned char *)&options :
                                        (unsigned char *)&device;
        p[byte] ^= 1u << bit;
        check(0, 0, 0, 0);
      }
  const uint64_t addresses[] = {0, 1, 2, 31, 32, UINT64_MAX-31, UINT64_MAX-255,
                                UINT64_MAX-65535};
  for (unsigned i = 0; i < sizeof(addresses)/sizeof(addresses[0]); ++i)
    for (unsigned stream = 0; stream < 3; ++stream) {
      fixture(128, 3, 137);
      if (stream == 0) plan.descriptor.q_base = addresses[i];
      if (stream == 1) plan.descriptor.k_base = addresses[i];
      if (stream == 2) plan.descriptor.v_base = addresses[i];
      check(0, 0, 0, 0);
    }
  const uint32_t scales[] = {0, 0x80000000, 1, 0x7f7fffff, 0x7f800000,
                             0xff800000, 0x7fc00000, 0x7f800001, 0xbf800000};
  for (unsigned i = 0; i < sizeof(scales)/sizeof(scales[0]); ++i) {
    fixture(128, 3, 137); memcpy(&plan.scale, &scales[i], sizeof(plan.scale));
    check(0, 0, 0, 0);
  }
  for (unsigned bits = 0; bits < 16; ++bits) {
    fixture(128, 3, 137); check(bits&1, bits&2, bits&4, bits&8);
  }
  printf("{\"cases\":%u,\"accepted\":%u,\"digest\":\"%016" PRIx64
         "\",\"direct_descriptor_checks\":%u,\"full_plan_checks\":%u,"
         "\"sample_direct_descriptor_checks\":%u,\"sample_full_plan_checks\":%u,"
         "\"feature_cases\":%u,\"feature_accepted\":%u}\n",
         cases, accepted, digest, descriptors, validators, sample_descriptors, sample_validators,
         feature_cases, feature_accepted);
  return 0;
}
