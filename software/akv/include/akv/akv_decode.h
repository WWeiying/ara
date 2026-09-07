#ifndef AKV_DECODE_H_
#define AKV_DECODE_H_

#include "akv.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Decode: Q/O [batch, query_head, D], K/V [batch, kv_head, token, D].
 * D is contiguous. Head/token axes of K/V may be exchanged using strides.
 * All strides are explicit bytes; only mask_batch_stride == 0 broadcasts.
 * Capacity is the accessible byte span, including padding, from each base.
 * This is not a paged-KV API. Inputs/descriptors must be immutable until return.
 */
typedef struct {
  const uint16_t *query, *key, *value, *mask;
  float *output;
  size_t query_bytes, key_bytes, value_bytes, mask_bytes, output_bytes;
  size_t q_head_stride, q_batch_stride;
  size_t k_token_stride, k_head_stride, k_batch_stride;
  size_t v_token_stride, v_head_stride, v_batch_stride;
  size_t mask_batch_stride, output_head_stride, output_batch_stride;
  uint32_t batches, query_heads, kv_heads, kv_length, head_dim;
  float scale;
} akv_decode_problem_t;

typedef akv_status_t (*akv_decode_group_executor_t)(
    void *context, const akv_attention_plan_t *plan,
    uint32_t batch, uint32_t first_query_head);

/* Validates every group, every buffer span and cross-group output aliasing.
 * No custom instruction, data conversion or output write occurs here.
 */
akv_status_t akv_decode_validate(const akv_device_t *device,
                                 const akv_decode_problem_t *problem,
                                 uint64_t *group_count);

/* Serial groups share one hardware context. Any callback failure returns
 * EXECUTION, even on the first group: it may already have written output.
 * Fallback is legal only before execution, never after EXECUTION.
 */
akv_status_t akv_decode_execute(const akv_device_t *device,
                                const akv_decode_problem_t *problem,
                                akv_decode_group_executor_t executor,
                                void *context, uint64_t *completed_groups);

#ifdef __cplusplus
}
#endif
#endif
