#ifndef AKV_PREFILL_INTERNAL_H_
#define AKV_PREFILL_INTERNAL_H_

#include "../include/akv/akv.h"

akv_status_t akv_attention_v2_prefill_validate(
    const akv_device_t *device,
    const akv_attention_v2_prefill_problem_t *problem,
    const akv_attention_v2_prefill_workspace_t *workspace,
    uint32_t *past_tokens, uint32_t *maximum_prefix);

#endif
