#ifndef AKV_EXPERIMENTAL_PAIR_ADMISSION_H
#define AKV_EXPERIMENTAL_PAIR_ADMISSION_H

#include "../../include/akv/akv.h"

/* Selection only: the caller must validate its plan and query capabilities
 * before FULL. This helper neither acquires a context nor issues a command. */
static inline int akv_pair_f16_admitted(
    unsigned requested, const akv_descriptor_t *descriptor,
    const akv_capabilities_t *capabilities) {
  if (requested != 1u || descriptor == NULL || capabilities == NULL)
    return 0;
  const unsigned heads = descriptor->q_rows;
  const unsigned dim = descriptor->head_dim;
  if (descriptor->element_format != AKV_ELEMENT_FORMAT_F16 ||
      heads < 2u || heads > AKV_MAX_Q_ROWS ||
      (dim != AKV_HEAD_DIM_64 && dim != AKV_HEAD_DIM_96 &&
       dim != AKV_HEAD_DIM_128) ||
      (heads == AKV_ATTENTION_KERNEL_Q_ROWS && dim == AKV_HEAD_DIM_128))
    return 0;
  return capabilities->valid && capabilities->enabled &&
         capabilities->f16_payload && capabilities->max_q_rows >= heads &&
         capabilities->context_count && capabilities->token_axis_valid &&
         capabilities->token_axis_enabled && capabilities->token_axis_tail &&
         capabilities->token_axis_row_view &&
         capabilities->token_axis_column_panel4 &&
         capabilities->token_axis_tile_tokens == AKV_V2_TILE_TOKENS &&
         (dim == AKV_HEAD_DIM_64 ? capabilities->head_dim_64 :
          dim == AKV_HEAD_DIM_96 ? capabilities->token_axis_d_axis_tail :
                                  capabilities->head_dim_128);
}

#endif
