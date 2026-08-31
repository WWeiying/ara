#include "../include/akv/akv.h"

#include <string.h>


static const uint16_t *row_address(uint64_t base, uint32_t stride,
                                   uint32_t index) {
  return (const uint16_t *)(uintptr_t)(base + (uint64_t)stride * index);
}


static akv_status_t validate_fill(const akv_descriptor_t *descriptor,
                                  uint32_t tile_start,
                                  uint32_t *tile_count) {
  if (descriptor == NULL || tile_count == NULL)
    return AKV_STATUS_BAD_ARGUMENT;
  if (!akv_descriptor_is_valid(descriptor))
    return AKV_STATUS_LAYOUT;
  const uint32_t count = akv_v2_tile_length(descriptor->kv_length, tile_start);
  if (count == 0u)
    return AKV_STATUS_RANGE;
  *tile_count = count;
  return AKV_STATUS_OK;
}


static void copy_q_rows(akv_v2_reference_context_t *context,
                        const akv_descriptor_t *descriptor) {
  const size_t row_bytes = (size_t)descriptor->head_dim * sizeof(uint16_t);
  memset(context->query, 0, sizeof(context->query));
  for (uint32_t row = 0; row < descriptor->q_rows; ++row)
    memcpy(context->query[row],
           row_address(descriptor->q_base,
                       descriptor->q_row_stride_bytes, row),
           row_bytes);
}


static void copy_kv_tile(akv_v2_reference_context_t *context,
                         const akv_descriptor_t *descriptor,
                         uint32_t tile_start, uint32_t tile_count) {
  const size_t row_bytes = (size_t)descriptor->head_dim * sizeof(uint16_t);
  memset(context->key, 0, sizeof(context->key));
  memset(context->value, 0, sizeof(context->value));
  for (uint32_t token = 0; token < tile_count; ++token) {
    const uint32_t source_token = tile_start + token;
    memcpy(context->key[token],
           row_address(descriptor->k_base,
                       descriptor->k_token_stride_bytes, source_token),
           row_bytes);
    memcpy(context->value[token],
           row_address(descriptor->v_base,
                       descriptor->v_token_stride_bytes, source_token),
           row_bytes);
  }
}


void akv_v2_reference_init(akv_v2_reference_context_t *context) {
  if (context != NULL)
    memset(context, 0, sizeof(*context));
}


akv_status_t akv_v2_reference_full(akv_v2_reference_context_t *context,
                                   const akv_descriptor_t *descriptor,
                                   uint32_t tile_start) {
  if (context == NULL)
    return AKV_STATUS_BAD_ARGUMENT;
  uint32_t tile_count;
  const akv_status_t status = validate_fill(descriptor, tile_start, &tile_count);
  if (status != AKV_STATUS_OK)
    return status;

  copy_q_rows(context, descriptor);
  copy_kv_tile(context, descriptor, tile_start, tile_count);
  context->descriptor = *descriptor;
  context->tile_start = (uint16_t)tile_start;
  context->tile_count = (uint16_t)tile_count;
  context->ready = 1u;
  return AKV_STATUS_OK;
}


akv_status_t akv_v2_reference_refill(akv_v2_reference_context_t *context,
                                     uint32_t tile_start) {
  if (context == NULL)
    return AKV_STATUS_BAD_ARGUMENT;
  if (!context->ready)
    return AKV_STATUS_EXECUTION;
  uint32_t tile_count;
  const akv_status_t status =
      validate_fill(&context->descriptor, tile_start, &tile_count);
  if (status != AKV_STATUS_OK)
    return status;

  copy_kv_tile(context, &context->descriptor, tile_start, tile_count);
  context->tile_start = (uint16_t)tile_start;
  context->tile_count = (uint16_t)tile_count;
  return AKV_STATUS_OK;
}


akv_status_t akv_v2_reference_load_row(
    const akv_v2_reference_context_t *context, uint32_t selector,
    uint16_t *destination, size_t destination_elements) {
  if (context == NULL || destination == NULL)
    return AKV_STATUS_BAD_ARGUMENT;
  if (!context->ready)
    return AKV_STATUS_EXECUTION;
  if (!akv_v2_row_selector_is_valid(&context->descriptor,
                                    context->tile_count, selector) ||
      destination_elements < context->descriptor.head_dim)
    return AKV_STATUS_RANGE;

  const uint32_t stream = akv_selector_stream(selector);
  const uint32_t index = akv_v2_selector_index(selector);
  const uint16_t *source;
  if (stream == AKV_STREAM_Q)
    source = context->query[index];
  else if (stream == AKV_STREAM_K)
    source = context->key[index];
  else
    source = context->value[index];
  memcpy(destination, source,
         (size_t)context->descriptor.head_dim * sizeof(uint16_t));
  return AKV_STATUS_OK;
}


akv_status_t akv_v2_reference_load_k_column(
    const akv_v2_reference_context_t *context, uint32_t dimension,
    uint16_t *destination, size_t destination_elements,
    size_t *active_elements) {
  if (context == NULL || destination == NULL || active_elements == NULL)
    return AKV_STATUS_BAD_ARGUMENT;
  if (!context->ready)
    return AKV_STATUS_EXECUTION;
  if (!akv_v2_column_is_valid(&context->descriptor, context->tile_count,
                              dimension) ||
      destination_elements < context->tile_count)
    return AKV_STATUS_RANGE;

  for (uint32_t token = 0; token < context->tile_count; ++token)
    destination[token] = context->key[token][dimension];
  *active_elements = context->tile_count;
  return AKV_STATUS_OK;
}


void akv_v2_reference_release(akv_v2_reference_context_t *context) {
  if (context != NULL)
    context->ready = 0u;
}
