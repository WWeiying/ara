#ifndef AKV_RUNTIME_H_
#define AKV_RUNTIME_H_

#include "akv_abi.h"

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define AKV_ATTENTION_KERNEL_VERSION_V1 1u
#define AKV_ATTENTION_KERNEL_VERSION_V2 2u
#define AKV_ATTENTION_KERNEL_VERSION AKV_ATTENTION_KERNEL_VERSION_V1
#define AKV_ATTENTION_KERNEL_Q_ROWS 6u
#define AKV_PREFILL_QUERY_BLOCK_TOKENS 64u

typedef enum {
  AKV_STATUS_OK = 0,
  AKV_STATUS_BAD_ARGUMENT,
  AKV_STATUS_RUNTIME_UNAVAILABLE,
  AKV_STATUS_ABI_MISMATCH,
  AKV_STATUS_CAPABILITY,
  AKV_STATUS_SHAPE,
  AKV_STATUS_LAYOUT,
  AKV_STATUS_RANGE,
  AKV_STATUS_ALIAS,
  AKV_STATUS_EXECUTION,
} akv_status_t;

typedef struct {
  uint8_t valid;
  uint8_t enabled;
  uint8_t architecture_version;
  uint8_t descriptor_version;
  uint8_t descriptor_bytes;
  uint8_t descriptor_alignment_log2;
  uint8_t max_q_rows;
  uint8_t tile_tokens;
  uint8_t context_count;
  uint8_t f16_payload;
  uint8_t head_dim_64;
  uint8_t head_dim_128;
  uint8_t token_axis_valid;
  uint8_t token_axis_enabled;
  uint8_t token_axis_profile_version;
  uint8_t token_axis_tile_tokens;
  uint8_t token_axis_banks;
  uint8_t token_axis_selector_index_bits;
  uint8_t token_axis_tail;
  uint8_t token_axis_row_view;
  uint8_t token_axis_d_axis_tail;
  uint8_t token_axis_d256_segmented;
} akv_capabilities_t;

typedef struct {
  akv_capabilities_t capabilities;
} akv_device_t;

typedef uint64_t (*akv_info_reader_t)(void *context, unsigned index);

typedef struct {
  const uint16_t *query;
  const uint16_t *key;
  const uint16_t *value;
  const uint16_t *mask;
  float *output;
  size_t q_row_stride_bytes;
  size_t k_token_stride_bytes;
  size_t v_token_stride_bytes;
  size_t output_row_stride_bytes;
  uint32_t q_rows;
  uint32_t head_dim;
  uint32_t kv_length;
  float scale;
} akv_attention_problem_t;

typedef struct __attribute__((aligned(AKV_DESCRIPTOR_BYTES))) {
  /* Primary command descriptor; for D256 this maps Q0/K0/K1 as D128 rows. */
  akv_descriptor_t descriptor;
  /* D256 value phase descriptor; maps Q1/V0/V1 into the same physical slots. */
  akv_descriptor_t value_descriptor;
  const uint16_t *mask;
  float *output;
  size_t output_row_stride_bytes;
  float scale;
  uint32_t kernel_version;
  uint16_t logical_head_dim;
  uint16_t d_offset;
  uint16_t d_count;
  uint8_t d_segment_count;
  uint8_t reserved[1];
} akv_attention_plan_t;

typedef struct __attribute__((aligned(AKV_DESCRIPTOR_BYTES))) {
  uint16_t accumulator[AKV_MAX_Q_ROWS][AKV_HEAD_DIM_256];
  float score[AKV_MAX_Q_ROWS][AKV_V2_TILE_TOKENS];
  float maximum[AKV_MAX_Q_ROWS];
  float sum[AKV_MAX_Q_ROWS];
  float old_scale[AKV_MAX_Q_ROWS];
} akv_attention_v2_workspace_t;

/*
 * Contiguous batch-one Prefill layout:
 *   Query  F32 [query_heads][query_tokens][head_dim]
 *   Key/V  F16 [kv_heads][kv_capacity][head_dim]
 *   mask   F16 [query_tokens][kv_capacity]
 *   output F32 [query_tokens][query_heads][head_dim]
 */
typedef struct {
  const float *query;
  const uint16_t *key;
  const uint16_t *value;
  const uint16_t *mask;
  float *output;
  uint32_t query_tokens;
  uint32_t query_heads;
  uint32_t kv_heads;
  uint32_t kv_capacity;
  uint32_t head_dim;
  float scale;
} akv_attention_v2_prefill_problem_t;

/* Fixed hidden state for one GQA group and one 64-Query block. */
typedef struct __attribute__((aligned(AKV_DESCRIPTOR_BYTES))) {
  /* Keep the GQA rows consumed together by one score kernel contiguous. */
  uint16_t query[AKV_PREFILL_QUERY_BLOCK_TOKENS][AKV_MAX_Q_ROWS]
                [AKV_HEAD_DIM_128];
  akv_attention_plan_t plan;
  float score[AKV_MAX_Q_ROWS][AKV_V2_TILE_TOKENS];
  float maximum[AKV_PREFILL_QUERY_BLOCK_TOKENS][AKV_MAX_Q_ROWS];
  float sum[AKV_PREFILL_QUERY_BLOCK_TOKENS][AKV_MAX_Q_ROWS];
  float old_scale[AKV_MAX_Q_ROWS];
} akv_attention_v2_prefill_workspace_t;

typedef akv_status_t (*akv_attention_executor_t)(
    void *context, const akv_descriptor_t *descriptor, const uint16_t *mask,
    float *output, size_t output_row_stride_bytes, float scale);

/*
 * Functional AKV-v2 context model.  It models visible command semantics and
 * element ordering, not memory latency or implementation banking.
 */
typedef struct __attribute__((aligned(AKV_DESCRIPTOR_BYTES))) {
  akv_descriptor_t descriptor;
  uint16_t query[AKV_MAX_Q_ROWS][AKV_HEAD_DIM_128];
  uint16_t key[AKV_V2_TILE_TOKENS][AKV_HEAD_DIM_128];
  uint16_t value[AKV_V2_TILE_TOKENS][AKV_HEAD_DIM_128];
  uint16_t tile_start;
  uint16_t tile_count;
  uint8_t ready;
  uint8_t reserved[3];
} akv_v2_reference_context_t;

const char *akv_status_string(akv_status_t status);

akv_status_t akv_capabilities_decode(uint64_t info0, uint64_t info1,
                                     akv_capabilities_t *capabilities);
akv_status_t akv_capabilities_decode_extended(
    uint64_t info0, uint64_t info1, uint64_t info2, uint64_t info3,
    akv_capabilities_t *capabilities);
akv_status_t akv_device_query(akv_info_reader_t reader, void *context,
                              akv_device_t *device);
akv_status_t akv_device_init_reference(akv_device_t *device);

/* AKV-v2 accepts any Query group that fits the advertised context capacity. */
int akv_attention_v2_shape_supported(uint32_t q_rows, uint32_t head_dim);
int akv_attention_plan_v2_is_valid(const akv_attention_plan_t *plan);

akv_status_t akv_attention_plan_create(const akv_device_t *device,
                                       const akv_attention_problem_t *problem,
                                       akv_attention_plan_t *plan);
akv_status_t akv_attention_plan_create_v2(
    const akv_device_t *device, const akv_attention_problem_t *problem,
    akv_attention_plan_t *plan);
akv_status_t akv_attention_execute(const akv_attention_plan_t *plan,
                                   akv_attention_executor_t executor,
                                   void *executor_context);
akv_status_t akv_attention_execute_v2(const akv_attention_plan_t *plan,
                                      akv_attention_executor_t executor,
                                      void *executor_context);

void akv_v2_reference_init(akv_v2_reference_context_t *context);
akv_status_t akv_v2_reference_full(akv_v2_reference_context_t *context,
                                   const akv_descriptor_t *descriptor,
                                   uint32_t tile_start);
akv_status_t akv_v2_reference_refill(akv_v2_reference_context_t *context,
                                     uint32_t tile_start);
akv_status_t akv_v2_reference_load_row(
    const akv_v2_reference_context_t *context, uint32_t selector,
    uint16_t *destination, size_t destination_elements);
akv_status_t akv_v2_reference_load_k_column(
    const akv_v2_reference_context_t *context, uint32_t dimension,
    uint16_t *destination, size_t destination_elements,
    size_t *active_elements);
akv_status_t akv_v2_reference_load_column(
    const akv_v2_reference_context_t *context, uint32_t selector,
    uint16_t *destination, size_t destination_elements,
    size_t *active_elements);
void akv_v2_reference_release(akv_v2_reference_context_t *context);

/* Execute an immutable plan returned by akv_attention_plan_create(). */
akv_status_t akv_attention_execute_native(const akv_attention_plan_t *plan);
akv_status_t akv_attention_execute_v2_native(
    const akv_attention_plan_t *plan,
    akv_attention_v2_workspace_t *workspace);
akv_status_t akv_attention_execute_v2_prefill_native(
    const akv_device_t *device,
    const akv_attention_v2_prefill_problem_t *problem,
    akv_attention_v2_prefill_workspace_t *workspace);

/* Call akv_native_info only after a trap-safe platform capability check. */
uint64_t akv_native_info(void *context, unsigned index);
akv_status_t akv_native_execute(void *context,
                                const akv_descriptor_t *descriptor,
                                const uint16_t *mask, float *output,
                                size_t output_row_stride_bytes, float scale);

#ifdef __cplusplus
}
#endif

#endif
