#include "akv/akv.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>

enum {
  TEST_KV_LENGTH = 16,
  TEST_ROW_ELEMENTS = AKV_HEAD_DIM_128,
};

static _Alignas(
    64) uint16_t query[AKV_ATTENTION_KERNEL_Q_ROWS * TEST_ROW_ELEMENTS];
static _Alignas(64) uint16_t key[TEST_KV_LENGTH * TEST_ROW_ELEMENTS];
static _Alignas(64) uint16_t value[TEST_KV_LENGTH * TEST_ROW_ELEMENTS];
static _Alignas(64) uint16_t mask[TEST_KV_LENGTH];
static _Alignas(
    64) float output[AKV_ATTENTION_KERNEL_Q_ROWS * TEST_ROW_ELEMENTS];

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

  akv_capabilities_t capabilities;
  assert(akv_capabilities_decode(0u, 0u, &capabilities) ==
         AKV_STATUS_RUNTIME_UNAVAILABLE);
  assert(akv_capabilities_decode(akv_capability_word(0u, 1) ^ 1u,
                                 akv_capability_word(1u, 1),
                                 &capabilities) == AKV_STATUS_ABI_MISMATCH);
  assert(akv_capabilities_decode(akv_capability_word(0u, 0),
                                 akv_capability_word(1u, 0), &capabilities) ==
         AKV_STATUS_RUNTIME_UNAVAILABLE);
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
  assert(strcmp(akv_status_string(AKV_STATUS_LAYOUT), "layout") == 0);
#if !defined(__riscv)
  assert(akv_native_info(NULL, 0u) == 0u);
#endif
  return 0;
}
