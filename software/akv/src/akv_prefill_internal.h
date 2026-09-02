#ifndef AKV_PREFILL_INTERNAL_H_
#define AKV_PREFILL_INTERNAL_H_

#include "../include/akv/akv.h"

typedef struct {
  uint32_t query_token_stride_bytes;
  uint32_t query_head_stride_bytes;
  uint32_t key_token_stride_bytes;
  uint32_t key_head_stride_bytes;
  uint32_t value_token_stride_bytes;
  uint32_t value_head_stride_bytes;
  uint32_t mask_token_stride_bytes;
  uint32_t output_token_stride_bytes;
} akv_attention_v2_prefill_layout_t;

akv_status_t akv_attention_v2_prefill_validate(
    const akv_device_t *device,
    const akv_attention_v2_prefill_problem_t *problem,
    const akv_attention_v2_prefill_workspace_t *workspace,
    uint32_t *past_tokens, uint32_t *maximum_prefix,
    akv_attention_v2_prefill_layout_t *layout);

#endif
