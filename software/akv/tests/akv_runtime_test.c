#include "akv/akv.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>

enum {
  TEST_KV_LENGTH = 16,
  V2_TEST_KV_LENGTH = 65,
  TEST_ROW_ELEMENTS = AKV_HEAD_DIM_128,
};

static _Alignas(
    64) uint16_t query[AKV_ATTENTION_KERNEL_Q_ROWS * TEST_ROW_ELEMENTS];
static _Alignas(64) uint16_t key[TEST_KV_LENGTH * TEST_ROW_ELEMENTS];
static _Alignas(64) uint16_t value[TEST_KV_LENGTH * TEST_ROW_ELEMENTS];
static _Alignas(64) uint16_t mask[TEST_KV_LENGTH];
static _Alignas(
    64) float output[AKV_ATTENTION_KERNEL_Q_ROWS * TEST_ROW_ELEMENTS];
static _Alignas(64) uint16_t
    v2_key[V2_TEST_KV_LENGTH * TEST_ROW_ELEMENTS];
static _Alignas(64) uint16_t
    v2_value[V2_TEST_KV_LENGTH * TEST_ROW_ELEMENTS];
static _Alignas(64) akv_v2_reference_context_t v2_context;

typedef struct {
  unsigned calls;
  const akv_descriptor_t *descriptor;
  const uint16_t *mask;
  float *output;
  size_t output_stride;
  float scale;
} executor_capture_t;

static akv_status_t capture_executor(void *context,
                                     const akv_descriptor_t *descriptor,
                                     const uint16_t *mask_address,
                                     float *output_address,
                                     size_t output_stride, float scale) {
  executor_capture_t *capture = (executor_capture_t *)context;
  capture->calls++;
  capture->descriptor = descriptor;
  capture->mask = mask_address;
  capture->output = output_address;
  capture->output_stride = output_stride;
  capture->scale = scale;
  return AKV_STATUS_OK;
}

static akv_attention_problem_t valid_problem(void) {
  return (akv_attention_problem_t){
      .query = query,
      .key = key,
      .value = value,
      .mask = mask,
      .output = output,
      .q_row_stride_bytes = TEST_ROW_ELEMENTS * sizeof(uint16_t),
      .k_token_stride_bytes = TEST_ROW_ELEMENTS * sizeof(uint16_t),
      .v_token_stride_bytes = TEST_ROW_ELEMENTS * sizeof(uint16_t),
      .output_row_stride_bytes = TEST_ROW_ELEMENTS * sizeof(float),
      .q_rows = AKV_ATTENTION_KERNEL_Q_ROWS,
      .head_dim = AKV_HEAD_DIM_128,
      .kv_length = TEST_KV_LENGTH,
      .scale = 0.0883883476f,
  };
}

static void test_capabilities(void) {
  akv_device_t device;
  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);
  assert(device.capabilities.valid == 1u);
  assert(device.capabilities.enabled == 1u);
  assert(device.capabilities.f16_payload == 1u);
  assert(device.capabilities.head_dim_64 == 1u);
  assert(device.capabilities.head_dim_128 == 1u);
  assert(device.capabilities.token_axis_valid == 1u);
  assert(device.capabilities.token_axis_enabled == 1u);
  assert(device.capabilities.token_axis_profile_version ==
         AKV_V2_PROFILE_VERSION);
  assert(device.capabilities.token_axis_tile_tokens == AKV_V2_TILE_TOKENS);
  assert(device.capabilities.token_axis_banks == AKV_V2_TOKEN_BANKS);

  akv_capabilities_t capabilities;
  assert(akv_capabilities_decode(0u, 0u, &capabilities) ==
         AKV_STATUS_RUNTIME_UNAVAILABLE);
  assert(akv_capabilities_decode(akv_capability_word(0u, 1) ^ 1u,
                                 akv_capability_word(1u, 1),
                                 &capabilities) == AKV_STATUS_ABI_MISMATCH);
  assert(akv_capabilities_decode(akv_capability_word(0u, 0),
                                 akv_capability_word(1u, 0), &capabilities) ==
         AKV_STATUS_RUNTIME_UNAVAILABLE);

  assert(akv_capabilities_decode_extended(
             akv_capability_word(0u, 1), akv_capability_word(1u, 1),
             0u, 0u, &capabilities) == AKV_STATUS_OK);
  assert(capabilities.token_axis_valid == 0u);
  assert(akv_capabilities_decode_extended(
             akv_capability_word(0u, 1), akv_capability_word(1u, 1),
             akv_v2_capability_word(2u, 1), 0u, &capabilities) ==
         AKV_STATUS_ABI_MISMATCH);
}

static void test_v2_reference_context(void) {
  for (size_t token = 0; token < V2_TEST_KV_LENGTH; ++token) {
    for (size_t dimension = 0; dimension < TEST_ROW_ELEMENTS; ++dimension) {
      v2_key[token * TEST_ROW_ELEMENTS + dimension] =
          (uint16_t)(0x1000u + token * 0x80u + dimension);
      v2_value[token * TEST_ROW_ELEMENTS + dimension] =
          (uint16_t)(0x8000u + token * 0x40u + dimension);
    }
  }

  akv_attention_problem_t problem = valid_problem();
  problem.key = v2_key;
  problem.value = v2_value;
  problem.kv_length = V2_TEST_KV_LENGTH;
  akv_device_t device;
  akv_attention_plan_t plan;
  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);
  assert(akv_attention_plan_create(&device, &problem, &plan) == AKV_STATUS_OK);

  akv_v2_reference_init(&v2_context);
  assert(akv_v2_reference_full(&v2_context, &plan.descriptor, 0u) ==
         AKV_STATUS_OK);
  assert(v2_context.ready == 1u);
  assert(v2_context.tile_count == AKV_V2_TILE_TOKENS);

  uint16_t observed[AKV_HEAD_DIM_128];
  uint16_t sentinel[AKV_HEAD_DIM_128];
  for (size_t index = 0; index < AKV_HEAD_DIM_128; ++index)
    sentinel[index] = (uint16_t)(0xf000u + index);
  memcpy(observed, sentinel, sizeof(observed));

  assert(akv_v2_reference_load_row(
             &v2_context, akv_v2_selector(AKV_STREAM_V, 63), observed,
             AKV_HEAD_DIM_128) == AKV_STATUS_OK);
  assert(memcmp(observed, &v2_value[63u * TEST_ROW_ELEMENTS],
                sizeof(observed)) == 0);

  size_t active = 0u;
  assert(akv_v2_reference_load_k_column(
             &v2_context, 17u, observed, AKV_HEAD_DIM_128, &active) ==
         AKV_STATUS_OK);
  assert(active == 64u);
  for (size_t token = 0; token < active; ++token)
    assert(observed[token] == v2_key[token * TEST_ROW_ELEMENTS + 17u]);

  memcpy(observed, sentinel, sizeof(observed));
  assert(akv_v2_reference_load_k_column(
             &v2_context, AKV_HEAD_DIM_128, observed, AKV_HEAD_DIM_128,
             &active) == AKV_STATUS_RANGE);
  assert(memcmp(observed, sentinel, sizeof(observed)) == 0);

  assert(akv_v2_reference_refill(&v2_context, 64u) == AKV_STATUS_OK);
  assert(v2_context.tile_start == 64u);
  assert(v2_context.tile_count == 1u);
  active = 0u;
  assert(akv_v2_reference_load_k_column(
             &v2_context, 127u, observed, AKV_HEAD_DIM_128, &active) ==
         AKV_STATUS_OK);
  assert(active == 1u);
  assert(observed[0] == v2_key[64u * TEST_ROW_ELEMENTS + 127u]);

  const uint16_t old_tile_start = v2_context.tile_start;
  assert(akv_v2_reference_refill(&v2_context, 65u) == AKV_STATUS_RANGE);
  assert(v2_context.ready == 1u);
  assert(v2_context.tile_start == old_tile_start);

  memcpy(observed, sentinel, sizeof(observed));
  assert(akv_v2_reference_load_row(
             &v2_context, akv_v2_selector(AKV_STREAM_V, 1), observed,
             AKV_HEAD_DIM_128) == AKV_STATUS_RANGE);
  assert(memcmp(observed, sentinel, sizeof(observed)) == 0);

  akv_v2_reference_release(&v2_context);
  assert(v2_context.ready == 0u);
  assert(akv_v2_reference_load_k_column(
             &v2_context, 0u, observed, AKV_HEAD_DIM_128, &active) ==
         AKV_STATUS_EXECUTION);
}

static void test_plan_and_execute(void) {
  akv_device_t device;
  akv_attention_plan_t plan;
  akv_attention_problem_t problem = valid_problem();
  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);
  assert(akv_attention_plan_create(&device, &problem, &plan) == AKV_STATUS_OK);
  assert(((uintptr_t)&plan.descriptor & (AKV_DESCRIPTOR_BYTES - 1u)) == 0u);
  assert(plan.descriptor.q_base == (uint64_t)(uintptr_t)query);
  assert(plan.descriptor.kv_length == TEST_KV_LENGTH);
  assert(plan.descriptor.q_rows == AKV_ATTENTION_KERNEL_Q_ROWS);
  assert(akv_descriptor_is_valid(&plan.descriptor));

  executor_capture_t capture;
  memset(&capture, 0, sizeof(capture));
  assert(akv_attention_execute(&plan, capture_executor, &capture) ==
         AKV_STATUS_OK);
  assert(capture.calls == 1u);
  assert(capture.descriptor == &plan.descriptor);
  assert(capture.mask == mask);
  assert(capture.output == output);
  assert(capture.output_stride == TEST_ROW_ELEMENTS * sizeof(float));
  assert(capture.scale == problem.scale);
#if !defined(__riscv)
  assert(akv_attention_execute_native(&plan) == AKV_STATUS_RUNTIME_UNAVAILABLE);
#endif
  assert(akv_attention_execute_native(NULL) == AKV_STATUS_BAD_ARGUMENT);
}

static void test_rejections(void) {
  akv_device_t device;
  akv_attention_plan_t plan;
  akv_attention_problem_t problem = valid_problem();
  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);

  problem.q_rows = 5u;
  assert(akv_attention_plan_create(&device, &problem, &plan) ==
         AKV_STATUS_SHAPE);
  problem = valid_problem();
  problem.head_dim = AKV_HEAD_DIM_64;
  assert(akv_attention_plan_create(&device, &problem, &plan) ==
         AKV_STATUS_SHAPE);
  problem = valid_problem();
  problem.mask = NULL;
  assert(akv_attention_plan_create(&device, &problem, &plan) ==
         AKV_STATUS_BAD_ARGUMENT);
  problem = valid_problem();
  problem.output = (float *)(void *)query;
  assert(akv_attention_plan_create(&device, &problem, &plan) ==
         AKV_STATUS_ALIAS);
  problem = valid_problem();
  problem.k_token_stride_bytes--;
  assert(akv_attention_plan_create(&device, &problem, &plan) ==
         AKV_STATUS_LAYOUT);
  problem = valid_problem();
  problem.query = (const uint16_t *)(UINTPTR_MAX - 1u);
  assert(akv_attention_plan_create(&device, &problem, &plan) ==
         AKV_STATUS_RANGE);
  problem = valid_problem();
  problem.scale = 0.0f;
  assert(akv_attention_plan_create(&device, &problem, &plan) ==
         AKV_STATUS_BAD_ARGUMENT);

  device.capabilities.head_dim_128 = 0u;
  problem = valid_problem();
  assert(akv_attention_plan_create(&device, &problem, &plan) ==
         AKV_STATUS_CAPABILITY);
}

int main(void) {
  test_capabilities();
  test_plan_and_execute();
  test_rejections();
  test_v2_reference_context();
  assert(strcmp(akv_status_string(AKV_STATUS_LAYOUT), "layout") == 0);
#if !defined(__riscv)
  assert(akv_native_info(NULL, 0u) == 0u);
#endif
  return 0;
}
