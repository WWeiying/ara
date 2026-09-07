#include <stdint.h>
#include "printf.h"
#include <string.h>
#include "../../software/akv/include/akv/akv_features.h"

static uint16_t query[64] __attribute__((aligned(64)));
static uint16_t keys[65][64] __attribute__((aligned(64)));
static uint16_t values[65][64] __attribute__((aligned(64)));
static uint16_t mask[65] __attribute__((aligned(64)));
static float output[64] __attribute__((aligned(64)));
static akv_attention_v2_workspace_t workspace;

static uint64_t cycle(void) {
  uint64_t value;
  __asm__ volatile("csrr %0, cycle" : "=r"(value) : : "memory");
  return value;
}

int main(void) {
  akv_device_t device;
  if (akv_device_query(akv_native_info, NULL, &device) != AKV_STATUS_OK) return 1;
  for (unsigned t = 0; t < 65; ++t)
    for (unsigned d = 0; d < 64; ++d) values[t][d] = 0x4000u;
  akv_attention_problem_t problem = {
      .query = query, .key = &keys[0][0], .value = &values[0][0],
      .mask = mask, .output = output, .q_row_stride_bytes = 128,
      .k_token_stride_bytes = 128, .v_token_stride_bytes = 128,
      .output_row_stride_bytes = 256, .q_rows = 1, .head_dim = 64,
      .kv_length = 65, .scale = 0.125f,
  };
  akv_attention_plan_t plan;
  if (akv_attention_plan_create_v2(&device, &problem, &plan) != AKV_STATUS_OK) return 2;
  for (unsigned test = 0; test < 6; ++test) {
    akv_attention_features_t features = {0};
    float expected = 2.0f;
    memset(mask, 0, sizeof(mask));
    if (test <= 1u) {
      for (unsigned t = 0; t < 64; ++t) mask[t] = 0xfc00u;
      if (test == 1u) { features.sinks_enabled = 1; expected = 1.0f; }
    } else if (test == 2u) {
      features.window_enabled = 1; features.query_position = 64;
    } else if (test == 3u) {
      for (unsigned t = 0; t < 65; ++t) mask[t] = 0xfc00u;
      expected = 0.0f;
    } else if (test == 4u) {
      features.softcap = 2.0f;
      features.position_bias_enabled = 1; features.position_slope[0] = 0.25f;
      features.mask_scale_enabled = 1; features.mask_scale[0] = 0.5f;
      features.query_position = 64;
    }
    const uint64_t begin = cycle();
    akv_status_t status = test == 5u
        ? akv_attention_execute_v2_native(&plan, &workspace)
        : akv_attention_execute_v2_with_features_native(&plan, &workspace, &features);
    const uint64_t elapsed = cycle() - begin;
    unsigned errors = status != AKV_STATUS_OK;
    for (unsigned d = 0; d < 64; ++d) {
      const float diff = output[d] - expected;
      if (!(diff >= -0.004f && diff <= 0.004f)) ++errors;
    }
    printf("AKV_PORTABLE case=%u status=%u errors=%u cycles=%lu\n",
           test, status, errors, (unsigned long)elapsed);
    if (errors) return 3;
  }
  // Nonconstant data makes score processing observable in the final output.
  query[0] = 0x3c00u;
  for (unsigned t = 0; t < 65; ++t) {
    keys[t][0] = t % 3u == 0 ? 0xbc00u : t % 3u == 1 ? 0 : 0x3c00u;
    mask[t] = t % 7u == 0 ? 0xfc00u : 0xb400u;
    for (unsigned d = 0; d < 64; ++d)
      values[t][d] = (uint16_t)(0x3400u + ((t + d) % 3u) * 0x0400u);
  }
  problem.scale = 1.0f;
  if (akv_attention_plan_create_v2(&device, &problem, &plan) != AKV_STATUS_OK) return 4;
  akv_attention_features_t mixed = {0};
  mixed.softcap = 0.5f;
  mixed.mask_scale_enabled = 1; mixed.mask_scale[0] = 0.5f;
  mixed.position_bias_enabled = 1; mixed.position_slope[0] = 0.00390625f;
  mixed.sinks_enabled = 1; mixed.sinks[0] = 0.25f;
  mixed.query_position = 64;
  if (akv_attention_execute_v2_with_features_reference(&plan, &mixed) != AKV_STATUS_OK) return 5;
  float expected[64];
  memcpy(expected, output, sizeof(expected));
  if (akv_attention_execute_v2_with_features_native(&plan, &workspace, &mixed) != AKV_STATUS_OK) return 6;
  unsigned errors = 0;
  for (unsigned d = 0; d < 64; ++d) {
    const float diff = output[d] - expected[d];
    if (!(diff >= -0.004f && diff <= 0.004f)) ++errors;
  }
  printf("AKV_PORTABLE mixed_nonzero errors=%u\n", errors);
  if (errors) return 7;
  printf("AKV native portability smoke: PASS\n");
  return 0;
}
