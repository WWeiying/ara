#include "akv/akv.h"

#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <string.h>

enum {
  TEST_KV_LENGTH = 16,
  MAX_TEST_KV_LENGTH = 1024,
  V2_TEST_KV_LENGTH = 65,
  TEST_ROW_ELEMENTS = AKV_HEAD_DIM_256,
  PREFILL_D96_M = 3,
  PREFILL_D96_Q_HEADS = 4,
  PREFILL_D96_KV_HEADS = 2,
  PREFILL_D96_KV = 5,
  PREFILL_TAIL_M = 65,
  PREFILL_TAIL_Q_HEADS = AKV_MAX_Q_ROWS,
};

static _Alignas(64) uint16_t query[AKV_MAX_Q_ROWS * TEST_ROW_ELEMENTS];
static _Alignas(64) uint16_t key[MAX_TEST_KV_LENGTH * TEST_ROW_ELEMENTS];
static _Alignas(64) uint16_t value[MAX_TEST_KV_LENGTH * TEST_ROW_ELEMENTS];
static _Alignas(64) uint16_t mask[MAX_TEST_KV_LENGTH];
static _Alignas(64) float output[AKV_MAX_Q_ROWS * TEST_ROW_ELEMENTS];
static _Alignas(64) uint16_t
    v2_key[V2_TEST_KV_LENGTH * TEST_ROW_ELEMENTS];
static _Alignas(64) uint16_t
    v2_value[V2_TEST_KV_LENGTH * TEST_ROW_ELEMENTS];
static _Alignas(64) akv_v2_reference_context_t v2_context;
static _Alignas(64) float prefill_query[2u * 2u * AKV_HEAD_DIM_64];
static _Alignas(64) uint16_t prefill_key[2u * AKV_HEAD_DIM_64];
static _Alignas(64) uint16_t prefill_value[2u * AKV_HEAD_DIM_64];
static _Alignas(64) uint16_t prefill_mask[2u * 2u];
static _Alignas(64) float prefill_output[2u * 2u * AKV_HEAD_DIM_64];
static _Alignas(64) float
    prefill_d96_query[PREFILL_D96_Q_HEADS * PREFILL_D96_M * AKV_HEAD_DIM_96];
static _Alignas(64) uint16_t
    prefill_d96_key[PREFILL_D96_KV_HEADS * PREFILL_D96_KV * AKV_HEAD_DIM_96];
static _Alignas(64) uint16_t
    prefill_d96_value[PREFILL_D96_KV_HEADS * PREFILL_D96_KV *
                      AKV_HEAD_DIM_96];
static _Alignas(64) uint16_t
    prefill_d96_mask[PREFILL_D96_M * PREFILL_D96_KV];
static _Alignas(64) float
    prefill_d96_output[PREFILL_D96_M * PREFILL_D96_Q_HEADS *
                       AKV_HEAD_DIM_96];
static _Alignas(64) float
    prefill_tail_query[PREFILL_TAIL_Q_HEADS * PREFILL_TAIL_M *
                       AKV_HEAD_DIM_128];
static _Alignas(64) uint16_t
    prefill_tail_key[PREFILL_TAIL_M * AKV_HEAD_DIM_128];
static _Alignas(64) uint16_t
    prefill_tail_value[PREFILL_TAIL_M * AKV_HEAD_DIM_128];
static _Alignas(64) uint16_t
    prefill_tail_mask[PREFILL_TAIL_M * PREFILL_TAIL_M];
static _Alignas(64) float
    prefill_tail_output[PREFILL_TAIL_M * PREFILL_TAIL_Q_HEADS *
                        AKV_HEAD_DIM_128];
static _Alignas(64) akv_attention_v2_prefill_workspace_t prefill_workspace;

static void assert_close(float actual, float expected) {
  assert(fabsf(actual - expected) <= 1.0e-5f);
}

typedef struct {
  unsigned calls;
  const akv_descriptor_t *descriptor;
  akv_descriptor_t descriptor_copy;
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
  capture->descriptor_copy = *descriptor;
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

static void expect_v2_plan_rejection(const akv_device_t *device,
                                     const akv_attention_problem_t *problem,
                                     akv_status_t expected) {
  akv_attention_plan_t plan;
  const uint8_t *bytes = (const uint8_t *)&plan;
  memset(&plan, 0xa5, sizeof(plan));
  assert(akv_attention_plan_create_v2(device, problem, &plan) == expected);
  for (size_t index = 0; index < sizeof(plan); ++index)
    assert(bytes[index] == 0u);
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
  assert(device.capabilities.token_axis_d_axis_tail == 1u);
  assert(device.capabilities.token_axis_d256_segmented == 1u);
  assert(device.capabilities.token_axis_column_panel4 == 1u);

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
  const uint64_t legacy_info2 = akv_v2_capability_word(2u, 1) &
      ~(UINT64_C(1) << AKV_V2_D_AXIS_TAIL_CAPABILITY_BIT);
  assert(akv_capabilities_decode_extended(
             akv_capability_word(0u, 1), akv_capability_word(1u, 1),
             legacy_info2, akv_v2_capability_word(3u, 1), &capabilities) ==
         AKV_STATUS_OK);
  assert(capabilities.token_axis_d_axis_tail == 0u);
  const uint64_t no_d256_info2 = akv_v2_capability_word(2u, 1) &
      ~(UINT64_C(1) << AKV_V2_D256_SEGMENTED_CAPABILITY_BIT);
  assert(akv_capabilities_decode_extended(
             akv_capability_word(0u, 1), akv_capability_word(1u, 1),
             no_d256_info2, akv_v2_capability_word(3u, 1), &capabilities) ==
         AKV_STATUS_OK);
  assert(capabilities.token_axis_d256_segmented == 0u);
  const uint64_t no_panel_info2 = akv_v2_capability_word(2u, 1) &
      ~(UINT64_C(1) << AKV_V2_COLUMN_PANEL_CAPABILITY_BIT);
  assert(akv_capabilities_decode_extended(
             akv_capability_word(0u, 1), akv_capability_word(1u, 1),
             no_panel_info2, akv_v2_capability_word(3u, 1), &capabilities) ==
         AKV_STATUS_OK);
  assert(capabilities.token_axis_column_panel4 == 0u);
}

static void test_v2_reference_context(void) {
  for (size_t row = 0; row < AKV_MAX_Q_ROWS; ++row) {
    for (size_t dimension = 0; dimension < TEST_ROW_ELEMENTS; ++dimension) {
      query[row * TEST_ROW_ELEMENTS + dimension] =
          (uint16_t)(0x0100u + row * 0x100u + dimension);
    }
  }
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
  assert(akv_v2_descriptor_is_valid(&plan.descriptor));

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

  uint16_t panel[AKV_V2_COLUMN_PANEL_WIDTH * AKV_V2_TILE_TOKENS];
  memset(panel, 0xa5, sizeof(panel));
  assert(akv_v2_reference_load_column_panel4(
             &v2_context, akv_v2_column_selector(0u, 20u), panel,
             sizeof(panel) / sizeof(panel[0]), &active) == AKV_STATUS_OK);
  assert(active == AKV_V2_TILE_TOKENS);
  for (size_t column = 0; column < AKV_V2_COLUMN_PANEL_WIDTH; ++column)
    for (size_t token = 0; token < active; ++token)
      assert(panel[column * AKV_V2_TILE_TOKENS + token] ==
             v2_key[token * TEST_ROW_ELEMENTS + 20u + column]);
  assert(akv_v2_reference_load_column_panel4(
             &v2_context, akv_v2_column_selector(0u, 18u), panel,
             sizeof(panel) / sizeof(panel[0]), &active) == AKV_STATUS_RANGE);

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

  for (size_t index = 0; index < sizeof(panel) / sizeof(panel[0]); ++index)
    panel[index] = UINT16_C(0xa55a);
  assert(akv_v2_reference_load_column_panel4(
             &v2_context, akv_v2_column_selector(0u, 124u), panel,
             sizeof(panel) / sizeof(panel[0]), &active) == AKV_STATUS_OK);
  assert(active == 1u);
  for (size_t column = 0; column < AKV_V2_COLUMN_PANEL_WIDTH; ++column) {
    assert(panel[column * AKV_V2_TILE_TOKENS] ==
           v2_key[64u * TEST_ROW_ELEMENTS + 124u + column]);
    for (size_t token = 1; token < AKV_V2_TILE_TOKENS; ++token)
      assert(panel[column * AKV_V2_TILE_TOKENS + token] ==
             UINT16_C(0xa55a));
  }

  const uint16_t old_tile_start = v2_context.tile_start;
  assert(akv_v2_reference_refill(&v2_context, 65u) == AKV_STATUS_RANGE);
  assert(v2_context.ready == 1u);
  assert(v2_context.tile_start == old_tile_start);

  akv_descriptor_t misaligned = plan.descriptor;
  misaligned.q_base += 2u;
  assert(akv_descriptor_is_valid(&misaligned));
  assert(!akv_v2_descriptor_is_valid(&misaligned));
  assert(akv_v2_reference_full(&v2_context, &misaligned, 0u) ==
         AKV_STATUS_LAYOUT);
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
  akv_attention_plan_t v2_plan;
  akv_attention_problem_t problem = valid_problem();
  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);
  assert(akv_attention_plan_create(&device, &problem, &plan) == AKV_STATUS_OK);
  assert(((uintptr_t)&plan.descriptor & (AKV_DESCRIPTOR_BYTES - 1u)) == 0u);
  assert(plan.descriptor.q_base == (uint64_t)(uintptr_t)query);
  assert(plan.descriptor.kv_length == TEST_KV_LENGTH);
  assert(plan.descriptor.q_rows == AKV_ATTENTION_KERNEL_Q_ROWS);
  assert(akv_descriptor_is_valid(&plan.descriptor));
  assert(plan.kernel_version == AKV_ATTENTION_KERNEL_VERSION_V1);
  assert(akv_attention_plan_create_v2(&device, &problem, &v2_plan) ==
         AKV_STATUS_OK);
  assert(v2_plan.kernel_version == AKV_ATTENTION_KERNEL_VERSION_V2);
  assert(akv_v2_descriptor_is_valid(&v2_plan.descriptor));

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
  memset(&capture, 0, sizeof(capture));
  assert(akv_attention_execute_v2(&v2_plan, capture_executor, &capture) ==
         AKV_STATUS_OK);
  assert(capture.calls == 1u);
  assert(capture.descriptor == &v2_plan.descriptor);
  assert(akv_attention_execute(&v2_plan, capture_executor, &capture) ==
         AKV_STATUS_BAD_ARGUMENT);
  assert(akv_attention_execute_v2(&plan, capture_executor, &capture) ==
         AKV_STATUS_BAD_ARGUMENT);
#if !defined(__riscv)
  assert(akv_attention_execute_native(&plan) == AKV_STATUS_RUNTIME_UNAVAILABLE);
  akv_attention_v2_workspace_t workspace;
  assert(akv_attention_execute_v2_native(&v2_plan, &workspace) ==
         AKV_STATUS_RUNTIME_UNAVAILABLE);
#endif
  assert(akv_attention_execute_native(NULL) == AKV_STATUS_BAD_ARGUMENT);
  assert(akv_attention_execute_v2_native(NULL, NULL) ==
         AKV_STATUS_BAD_ARGUMENT);
}

static void test_v2_shape_matrix(void) {
  static const uint32_t q_rows[] = {1u, 2u, 3u, 4u, 5u, 6u, 7u, 8u};
  static const uint32_t head_dims[] = {
      AKV_HEAD_DIM_64, AKV_HEAD_DIM_96, AKV_HEAD_DIM_128, AKV_HEAD_DIM_256,
  };
  static const uint32_t kv_lengths[] = {
      16u, 63u, 64u, 65u, 128u, 256u, 1024u,
  };
  akv_device_t device;
  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);

  for (size_t q = 0; q < sizeof(q_rows) / sizeof(q_rows[0]); ++q) {
    for (size_t d = 0; d < sizeof(head_dims) / sizeof(head_dims[0]); ++d) {
      for (size_t k = 0; k < sizeof(kv_lengths) / sizeof(kv_lengths[0]); ++k) {
        akv_attention_problem_t problem = valid_problem();
        problem.q_rows = q_rows[q];
        problem.head_dim = head_dims[d];
        problem.kv_length = kv_lengths[k];
        problem.q_row_stride_bytes = head_dims[d] * sizeof(uint16_t);
        problem.k_token_stride_bytes = head_dims[d] * sizeof(uint16_t);
        problem.v_token_stride_bytes = head_dims[d] * sizeof(uint16_t);
        problem.output_row_stride_bytes = head_dims[d] * sizeof(float);
        akv_attention_plan_t plan;
        assert(akv_attention_v2_shape_supported(problem.q_rows,
                                                problem.head_dim));
        assert(akv_attention_plan_create_v2(&device, &problem, &plan) ==
               AKV_STATUS_OK);
        assert(plan.descriptor.q_rows == q_rows[q]);
        assert(plan.descriptor.head_dim ==
               (head_dims[d] == AKV_HEAD_DIM_256 ? AKV_HEAD_DIM_128
                                                 : head_dims[d]));
        assert(plan.logical_head_dim == head_dims[d]);
        assert(plan.d_segment_count ==
               (head_dims[d] == AKV_HEAD_DIM_256 ? 2u : 1u));
        assert(akv_attention_plan_v2_is_valid(&plan));
        assert(plan.descriptor.kv_length == kv_lengths[k]);
        executor_capture_t capture;
        memset(&capture, 0, sizeof(capture));
        assert(akv_attention_execute_v2(&plan, capture_executor, &capture) ==
               AKV_STATUS_OK);
        assert(capture.calls == 1u);
        assert(capture.descriptor_copy.head_dim == head_dims[d]);
      }
    }
  }

  assert(akv_attention_v2_shape_supported(3u, AKV_HEAD_DIM_128));
  assert(akv_attention_v2_shape_supported(4u, AKV_HEAD_DIM_96));
  assert(akv_attention_v2_shape_supported(4u, AKV_HEAD_DIM_256));
}

static void test_v2_d256_segment_contract(void) {
  for (size_t row = 0; row < AKV_MAX_Q_ROWS; ++row) {
    for (size_t d = 0; d < AKV_HEAD_DIM_256; ++d)
      query[row * TEST_ROW_ELEMENTS + d] =
          (uint16_t)(0x0100u + row * 0x100u + d);
  }
  for (size_t token = 0; token < V2_TEST_KV_LENGTH; ++token) {
    for (size_t d = 0; d < AKV_HEAD_DIM_256; ++d) {
      key[token * TEST_ROW_ELEMENTS + d] =
          (uint16_t)(0x1000u + token * 0x100u + d);
      value[token * TEST_ROW_ELEMENTS + d] =
          (uint16_t)(0x8000u + token * 0x100u + d);
    }
  }

  akv_device_t device;
  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);
  akv_attention_problem_t problem = valid_problem();
  problem.q_rows = 4u;
  problem.head_dim = AKV_HEAD_DIM_256;
  problem.kv_length = V2_TEST_KV_LENGTH;
  akv_attention_plan_t plan;
  assert(akv_attention_plan_create_v2(&device, &problem, &plan) ==
         AKV_STATUS_OK);
  assert(plan.logical_head_dim == AKV_HEAD_DIM_256);
  assert(plan.d_offset == 0u);
  assert(plan.d_count == AKV_HEAD_DIM_128);
  assert(plan.d_segment_count == 2u);
  assert(plan.descriptor.head_dim == AKV_HEAD_DIM_128);
  assert(plan.descriptor.k_base == (uint64_t)(uintptr_t)key);
  assert(plan.descriptor.v_base ==
         (uint64_t)(uintptr_t)(key + AKV_HEAD_DIM_128));
  assert(plan.value_descriptor.q_base ==
         (uint64_t)(uintptr_t)(query + AKV_HEAD_DIM_128));
  assert(plan.value_descriptor.k_base == (uint64_t)(uintptr_t)value);
  assert(plan.value_descriptor.v_base ==
         (uint64_t)(uintptr_t)(value + AKV_HEAD_DIM_128));
  assert(akv_attention_plan_v2_is_valid(&plan));

  executor_capture_t capture;
  memset(&capture, 0, sizeof(capture));
  assert(akv_attention_execute_v2(&plan, capture_executor, &capture) ==
         AKV_STATUS_OK);
  assert(capture.calls == 1u);
  assert(capture.descriptor_copy.head_dim == AKV_HEAD_DIM_256);
  assert(capture.descriptor_copy.q_base == (uint64_t)(uintptr_t)query);
  assert(capture.descriptor_copy.k_base == (uint64_t)(uintptr_t)key);
  assert(capture.descriptor_copy.v_base == (uint64_t)(uintptr_t)value);

  uint16_t observed[AKV_HEAD_DIM_128];
  size_t active = 0u;
  akv_v2_reference_init(&v2_context);
  assert(akv_v2_reference_full(&v2_context, &plan.descriptor, 0u) ==
         AKV_STATUS_OK);
  assert(akv_v2_reference_load_column(
             &v2_context, akv_v2_column_selector(0u, 17u), observed,
             AKV_HEAD_DIM_128, &active) == AKV_STATUS_OK);
  assert(active == AKV_V2_TILE_TOKENS);
  for (size_t token = 0; token < active; ++token)
    assert(observed[token] == key[token * TEST_ROW_ELEMENTS + 17u]);
  assert(akv_v2_reference_load_column(
             &v2_context, akv_v2_column_selector(1u, 17u), observed,
             AKV_HEAD_DIM_128, &active) == AKV_STATUS_OK);
  for (size_t token = 0; token < active; ++token)
    assert(observed[token] ==
           key[token * TEST_ROW_ELEMENTS + AKV_HEAD_DIM_128 + 17u]);

  assert(akv_v2_reference_full(&v2_context, &plan.value_descriptor, 0u) ==
         AKV_STATUS_OK);
  assert(akv_v2_reference_load_row(
             &v2_context, akv_v2_selector(AKV_STREAM_K, 3u), observed,
             AKV_HEAD_DIM_128) == AKV_STATUS_OK);
  assert(memcmp(observed, value + 3u * TEST_ROW_ELEMENTS,
                AKV_HEAD_DIM_128 * sizeof(uint16_t)) == 0);
  assert(akv_v2_reference_load_row(
             &v2_context, akv_v2_selector(AKV_STREAM_V, 3u), observed,
             AKV_HEAD_DIM_128) == AKV_STATUS_OK);
  assert(memcmp(observed,
                value + 3u * TEST_ROW_ELEMENTS + AKV_HEAD_DIM_128,
                AKV_HEAD_DIM_128 * sizeof(uint16_t)) == 0);

  plan.d_count = AKV_HEAD_DIM_96;
  assert(!akv_attention_plan_v2_is_valid(&plan));
}

static void test_v2_unsupported_matrix(void) {
  static const uint32_t unsupported_q_rows[] = {0u, 9u};
  static const uint32_t unsupported_head_dims[] = {0u, 32u, 80u, 192u, 257u};
  akv_device_t device;
  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);

  for (size_t index = 0;
       index < sizeof(unsupported_q_rows) / sizeof(unsupported_q_rows[0]);
       ++index) {
    akv_attention_problem_t problem = valid_problem();
    problem.q_rows = unsupported_q_rows[index];
    assert(!akv_attention_v2_shape_supported(problem.q_rows,
                                             problem.head_dim));
    expect_v2_plan_rejection(&device, &problem, AKV_STATUS_SHAPE);
  }

  for (size_t index = 0;
       index < sizeof(unsupported_head_dims) /
                   sizeof(unsupported_head_dims[0]);
       ++index) {
    akv_attention_problem_t problem = valid_problem();
    problem.head_dim = unsupported_head_dims[index];
    assert(!akv_attention_v2_shape_supported(problem.q_rows,
                                             problem.head_dim));
    expect_v2_plan_rejection(&device, &problem, AKV_STATUS_SHAPE);
  }

  akv_attention_problem_t problem = valid_problem();
  problem.kv_length = 0u;
  expect_v2_plan_rejection(&device, &problem, AKV_STATUS_SHAPE);
  problem.kv_length = (size_t)UINT16_MAX + 1u;
  expect_v2_plan_rejection(&device, &problem, AKV_STATUS_SHAPE);

  problem = valid_problem();
  problem.q_rows = AKV_MAX_Q_ROWS;
  device.capabilities.max_q_rows = AKV_MAX_Q_ROWS - 1u;
  expect_v2_plan_rejection(&device, &problem, AKV_STATUS_CAPABILITY);

  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);
  problem = valid_problem();
  problem.head_dim = AKV_HEAD_DIM_96;
  problem.q_row_stride_bytes = AKV_HEAD_DIM_96 * sizeof(uint16_t);
  problem.k_token_stride_bytes = AKV_HEAD_DIM_96 * sizeof(uint16_t);
  problem.v_token_stride_bytes = AKV_HEAD_DIM_96 * sizeof(uint16_t);
  problem.output_row_stride_bytes = AKV_HEAD_DIM_96 * sizeof(float);
  device.capabilities.token_axis_d_axis_tail = 0u;
  expect_v2_plan_rejection(&device, &problem, AKV_STATUS_CAPABILITY);

  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);
  problem = valid_problem();
  problem.q_rows = 4u;
  problem.head_dim = AKV_HEAD_DIM_256;
  device.capabilities.token_axis_d256_segmented = 0u;
  expect_v2_plan_rejection(&device, &problem, AKV_STATUS_CAPABILITY);
}

static void test_v2_prefill_boundary(void) {
  akv_device_t device;
  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);
  memset(prefill_query, 0, sizeof(prefill_query));
  memset(prefill_key, 0, sizeof(prefill_key));
  for (uint32_t head = 0u; head < 2u; ++head) {
    for (uint32_t token = 0u; token < 2u; ++token)
      prefill_query[((size_t)head * 2u + token) * AKV_HEAD_DIM_64] = 1.0f;
  }
  prefill_key[0] = UINT16_C(0x3c00);
  prefill_key[AKV_HEAD_DIM_64] = UINT16_C(0x4000);
  for (size_t element = 0u; element < AKV_HEAD_DIM_64; ++element) {
    prefill_value[element] = UINT16_C(0x4000);
    prefill_value[AKV_HEAD_DIM_64 + element] = UINT16_C(0x4400);
  }
  prefill_mask[0] = 0u;
  prefill_mask[1] = UINT16_C(0xfc00);
  prefill_mask[2] = 0u;
  prefill_mask[3] = 0u;
  akv_attention_v2_prefill_problem_t problem = {
      .query = prefill_query,
      .key = prefill_key,
      .value = prefill_value,
      .mask = prefill_mask,
      .output = prefill_output,
      .query_tokens = 2u,
      .query_heads = 2u,
      .kv_heads = 1u,
      .kv_capacity = 2u,
      .head_dim = AKV_HEAD_DIM_64,
      .scale = 1.0f,
  };

  assert(sizeof(prefill_workspace) == 139520u);
  assert(((uintptr_t)&prefill_workspace.plan &
          (AKV_DESCRIPTOR_BYTES - 1u)) == 0u);
  assert(akv_attention_execute_v2_prefill_reference(
             &device, &problem, &prefill_workspace) == AKV_STATUS_OK);
  const float second_expected =
      (2.0f * expf(1.0f) + 4.0f * expf(2.0f)) /
      (expf(1.0f) + expf(2.0f));
  for (uint32_t head = 0u; head < 2u; ++head) {
    for (uint32_t dimension = 0u; dimension < AKV_HEAD_DIM_64; ++dimension) {
      assert_close(prefill_output[head * AKV_HEAD_DIM_64 + dimension], 2.0f);
      assert_close(prefill_output[(2u + head) * AKV_HEAD_DIM_64 + dimension],
                   second_expected);
    }
  }
#if !defined(__riscv)
  assert(akv_attention_execute_v2_prefill_native(
             &device, &problem, &prefill_workspace) ==
         AKV_STATUS_RUNTIME_UNAVAILABLE);
#endif
  prefill_mask[0] = UINT16_C(0x7e00);
  assert(akv_attention_execute_v2_prefill_reference(
             &device, &problem, &prefill_workspace) == AKV_STATUS_SHAPE);
  assert(akv_attention_execute_v2_prefill_native(
             &device, &problem, &prefill_workspace) == AKV_STATUS_SHAPE);
  prefill_mask[0] = 0u;
  problem.query_tokens = 1u;
  assert(akv_attention_execute_v2_prefill_native(
             &device, &problem, &prefill_workspace) == AKV_STATUS_SHAPE);
  problem.query_tokens = 2u;
  problem.kv_capacity = UINT16_MAX + 1u;
  assert(akv_attention_execute_v2_prefill_native(
             &device, &problem, &prefill_workspace) == AKV_STATUS_SHAPE);
  problem.kv_capacity = 2u;
  problem.output = prefill_query;
  assert(akv_attention_execute_v2_prefill_native(
             &device, &problem, &prefill_workspace) == AKV_STATUS_ALIAS);
  problem.output = (float *)(void *)&prefill_workspace;
  assert(akv_attention_execute_v2_prefill_native(
             &device, &problem, &prefill_workspace) == AKV_STATUS_ALIAS);
  problem.output = prefill_output;
  assert(akv_attention_execute_v2_prefill_native(NULL, NULL, NULL) ==
         AKV_STATUS_BAD_ARGUMENT);
}

static void test_v2_prefill_reference_d96_past_and_gqa(void) {
  akv_device_t device;
  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);
  memset(prefill_d96_query, 0, sizeof(prefill_d96_query));
  memset(prefill_d96_key, 0, sizeof(prefill_d96_key));
  for (uint32_t kv_head = 0u; kv_head < PREFILL_D96_KV_HEADS; ++kv_head) {
    for (uint32_t token = 0u; token < PREFILL_D96_KV; ++token) {
      const float value = (float)(kv_head * 10u + token + 1u);
      for (uint32_t dimension = 0u; dimension < AKV_HEAD_DIM_96;
           ++dimension) {
        prefill_d96_value
            [((size_t)kv_head * PREFILL_D96_KV + token) * AKV_HEAD_DIM_96 +
             dimension] = value == 1.0f   ? UINT16_C(0x3c00)
                          : value == 2.0f ? UINT16_C(0x4000)
                          : value == 3.0f ? UINT16_C(0x4200)
                          : value == 4.0f ? UINT16_C(0x4400)
                          : value == 5.0f ? UINT16_C(0x4500)
                          : value == 11.0f ? UINT16_C(0x4980)
                          : value == 12.0f ? UINT16_C(0x4a00)
                          : value == 13.0f ? UINT16_C(0x4a80)
                          : value == 14.0f ? UINT16_C(0x4b00)
                                           : UINT16_C(0x4b80);
      }
    }
  }
  for (uint32_t token = 0u; token < PREFILL_D96_M; ++token) {
    const uint32_t prefix = 3u + token;
    for (uint32_t sequence = 0u; sequence < PREFILL_D96_KV; ++sequence) {
      prefill_d96_mask[(size_t)token * PREFILL_D96_KV + sequence] =
          sequence < prefix ? 0u : UINT16_C(0xfc00);
    }
  }

  const akv_attention_v2_prefill_problem_t problem = {
      .query = prefill_d96_query,
      .key = prefill_d96_key,
      .value = prefill_d96_value,
      .mask = prefill_d96_mask,
      .output = prefill_d96_output,
      .query_tokens = PREFILL_D96_M,
      .query_heads = PREFILL_D96_Q_HEADS,
      .kv_heads = PREFILL_D96_KV_HEADS,
      .kv_capacity = PREFILL_D96_KV,
      .head_dim = AKV_HEAD_DIM_96,
      .scale = 0.125f,
  };
  assert(akv_attention_execute_v2_prefill_reference(
             &device, &problem, &prefill_workspace) == AKV_STATUS_OK);
  for (uint32_t token = 0u; token < PREFILL_D96_M; ++token) {
    const float mean = (float)(4u + token) * 0.5f;
    for (uint32_t head = 0u; head < PREFILL_D96_Q_HEADS; ++head) {
      const float expected = mean + (head / 2u) * 10.0f;
      for (uint32_t dimension = 0u; dimension < AKV_HEAD_DIM_96;
           ++dimension) {
        assert_close(
            prefill_d96_output
                [((size_t)token * PREFILL_D96_Q_HEADS + head) *
                     AKV_HEAD_DIM_96 +
                 dimension],
            expected);
      }
    }
  }
}

static void test_v2_prefill_reference_block_and_tile_tail(void) {
  akv_device_t device;
  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);
  memset(prefill_tail_query, 0, sizeof(prefill_tail_query));
  memset(prefill_tail_key, 0, sizeof(prefill_tail_key));
  for (uint32_t token = 0u; token < PREFILL_TAIL_M; ++token) {
    const uint16_t value_bits = token == 64u ? UINT16_C(0x4000)
                                              : UINT16_C(0x3c00);
    for (uint32_t dimension = 0u; dimension < AKV_HEAD_DIM_128;
         ++dimension)
      prefill_tail_value[(size_t)token * AKV_HEAD_DIM_128 + dimension] =
          value_bits;
    for (uint32_t sequence = 0u; sequence < PREFILL_TAIL_M; ++sequence) {
      prefill_tail_mask[(size_t)token * PREFILL_TAIL_M + sequence] =
          sequence <= token ? 0u : UINT16_C(0xfc00);
    }
  }

  const akv_attention_v2_prefill_problem_t problem = {
      .query = prefill_tail_query,
      .key = prefill_tail_key,
      .value = prefill_tail_value,
      .mask = prefill_tail_mask,
      .output = prefill_tail_output,
      .query_tokens = PREFILL_TAIL_M,
      .query_heads = PREFILL_TAIL_Q_HEADS,
      .kv_heads = 1u,
      .kv_capacity = PREFILL_TAIL_M,
      .head_dim = AKV_HEAD_DIM_128,
      .scale = 0.125f,
  };
  assert(akv_attention_execute_v2_prefill_reference(
             &device, &problem, &prefill_workspace) == AKV_STATUS_OK);
  for (uint32_t token = 0u; token < PREFILL_TAIL_M; ++token) {
    const float expected = token == 64u ? 66.0f / 65.0f : 1.0f;
    for (uint32_t head = 0u; head < PREFILL_TAIL_Q_HEADS; ++head) {
      for (uint32_t dimension = 0u; dimension < AKV_HEAD_DIM_128;
           ++dimension) {
        assert_close(
            prefill_tail_output
                [((size_t)token * PREFILL_TAIL_Q_HEADS + head) *
                     AKV_HEAD_DIM_128 +
                 dimension],
            expected);
      }
    }
  }
}

static void test_rejections(void) {
  akv_device_t device;
  akv_attention_plan_t plan;
  akv_attention_problem_t problem = valid_problem();
  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);

  _Alignas(AKV_DESCRIPTOR_BYTES) unsigned char misaligned_storage[
      sizeof(akv_attention_plan_t) + AKV_DESCRIPTOR_BYTES];
  memset(misaligned_storage, 0xa5, sizeof(misaligned_storage));
  akv_attention_plan_t *misaligned_plan =
      (akv_attention_plan_t *)(void *)(misaligned_storage + 1u);
  assert(akv_attention_plan_create_v2(&device, &problem, misaligned_plan) ==
         AKV_STATUS_LAYOUT);
  for (size_t byte = 0; byte < sizeof(misaligned_storage); ++byte)
    assert(misaligned_storage[byte] == 0xa5u);

  problem.q_rows = 5u;
  assert(akv_attention_plan_create(&device, &problem, &plan) ==
         AKV_STATUS_SHAPE);
  assert(akv_attention_plan_create_v2(&device, &problem, &plan) ==
         AKV_STATUS_OK);
  problem = valid_problem();
  problem.head_dim = AKV_HEAD_DIM_64;
  assert(akv_attention_plan_create(&device, &problem, &plan) ==
         AKV_STATUS_SHAPE);
  assert(akv_attention_plan_create_v2(&device, &problem, &plan) ==
         AKV_STATUS_OK);
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
  problem.head_dim = AKV_HEAD_DIM_64;
  problem.q_row_stride_bytes = AKV_HEAD_DIM_64 * sizeof(uint16_t);
  problem.k_token_stride_bytes = AKV_HEAD_DIM_64 * sizeof(uint16_t);
  problem.v_token_stride_bytes = AKV_HEAD_DIM_64 * sizeof(uint16_t);
  problem.output_row_stride_bytes = AKV_HEAD_DIM_64 * sizeof(float);
  assert(akv_attention_plan_create_v2(&device, &problem, &plan) ==
         AKV_STATUS_OK);
  device.capabilities.head_dim_64 = 0u;
  assert(akv_attention_plan_create_v2(&device, &problem, &plan) ==
         AKV_STATUS_CAPABILITY);

  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);
  problem = valid_problem();
  problem.query++;
  assert(akv_attention_plan_create(&device, &problem, &plan) == AKV_STATUS_OK);
  assert(akv_attention_plan_create_v2(&device, &problem, &plan) ==
         AKV_STATUS_LAYOUT);

  assert(akv_capabilities_decode_extended(
             akv_capability_word(0u, 1), akv_capability_word(1u, 1), 0u, 0u,
             &device.capabilities) == AKV_STATUS_OK);
  problem = valid_problem();
  assert(akv_attention_plan_create(&device, &problem, &plan) == AKV_STATUS_OK);
  assert(akv_attention_plan_create_v2(&device, &problem, &plan) ==
         AKV_STATUS_CAPABILITY);
}

int main(void) {
  test_capabilities();
  test_plan_and_execute();
  test_v2_shape_matrix();
  test_v2_d256_segment_contract();
  test_v2_unsupported_matrix();
  test_v2_prefill_boundary();
  test_v2_prefill_reference_d96_past_and_gqa();
  test_v2_prefill_reference_block_and_tile_tail();
  test_rejections();
  test_v2_reference_context();
  assert(strcmp(akv_status_string(AKV_STATUS_LAYOUT), "layout") == 0);
#if !defined(__riscv)
  assert(akv_native_info(NULL, 0u) == 0u);
#endif
  return 0;
}
