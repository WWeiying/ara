#include "akv/akv_decode.h"

static akv_status_t matrix_span(size_t row, uint32_t n0, size_t s0,
                                uint32_t n1, size_t s1, size_t *span) {
  size_t a, b, ae, be;
  if (!n0 || !n1 || !row) return AKV_STATUS_SHAPE;
  if (__builtin_mul_overflow((size_t)n0 - 1u, s0, &a) ||
      __builtin_mul_overflow((size_t)n1 - 1u, s1, &b) ||
      __builtin_add_overflow(a, row, &ae) ||
      __builtin_add_overflow(b, row, &be) ||
      __builtin_add_overflow(a, be, span)) return AKV_STATUS_RANGE;
  if (!(((n0 == 1u || s0 >= row) && (n1 == 1u || s1 >= ae)) ||
        ((n1 == 1u || s1 >= row) && (n0 == 1u || s0 >= be))))
    return AKV_STATUS_LAYOUT;
  return AKV_STATUS_OK;
}

static akv_status_t batch_span(size_t span, uint32_t batches, size_t stride,
                               size_t *total) {
  if (batches > 1u && stride < span) return AKV_STATUS_LAYOUT;
  size_t offset;
  if (__builtin_mul_overflow((size_t)batches - 1u, stride, &offset) ||
      __builtin_add_overflow(offset, span, total)) return AKV_STATUS_RANGE;
  return AKV_STATUS_OK;
}

static akv_status_t group_plan(const akv_device_t *device,
                               const akv_decode_problem_t *p,
                               uint32_t batch, uint32_t first_head,
                               uint32_t rows, akv_attention_plan_t *plan) {
  const uint32_t kv_head = first_head / (p->query_heads / p->kv_heads);
  const akv_attention_problem_t group = {
      .query = (const uint16_t *)((const char *)p->query +
          (size_t)batch * p->q_batch_stride + (size_t)first_head * p->q_head_stride),
      .key = (const uint16_t *)((const char *)p->key +
          (size_t)batch * p->k_batch_stride + (size_t)kv_head * p->k_head_stride),
      .value = (const uint16_t *)((const char *)p->value +
          (size_t)batch * p->v_batch_stride + (size_t)kv_head * p->v_head_stride),
      .mask = (const uint16_t *)((const char *)p->mask +
          (size_t)batch * p->mask_batch_stride),
      .output = (float *)((char *)p->output +
          (size_t)batch * p->output_batch_stride +
          (size_t)first_head * p->output_head_stride),
      .q_row_stride_bytes = p->q_head_stride,
      .k_token_stride_bytes = p->k_token_stride,
      .v_token_stride_bytes = p->v_token_stride,
      .output_row_stride_bytes = p->output_head_stride,
      .q_rows = rows, .head_dim = p->head_dim,
      .kv_length = p->kv_length, .scale = p->scale,
  };
  return akv_attention_plan_create_v2(device, &group, plan);
}

akv_status_t akv_decode_validate(const akv_device_t *device,
                                 const akv_decode_problem_t *p,
                                 uint64_t *group_count) {
  if (group_count) *group_count = 0;
  if (!device || !p) return AKV_STATUS_BAD_ARGUMENT;
  if (!p->batches || !p->query_heads || !p->kv_heads ||
      p->query_heads % p->kv_heads || !p->kv_length ||
      p->kv_length > UINT16_MAX ||
      !akv_attention_v2_shape_supported(1u, p->head_dim)) return AKV_STATUS_SHAPE;
  const uint32_t limit = device->capabilities.max_q_rows;
  if (!limit || limit > AKV_MAX_Q_ROWS) return AKV_STATUS_CAPABILITY;
  const size_t row = p->head_dim * sizeof(uint16_t);
  size_t spans[5];
  akv_status_t status;
#define CHECK(expr) do { status = (expr); if (status != AKV_STATUS_OK) return status; } while (0)
  CHECK(matrix_span(row, p->query_heads, p->q_head_stride, 1u, 0u, &spans[0]));
  CHECK(matrix_span(row, p->kv_length, p->k_token_stride,
                    p->kv_heads, p->k_head_stride, &spans[1]));
  CHECK(matrix_span(row, p->kv_length, p->v_token_stride,
                    p->kv_heads, p->v_head_stride, &spans[2]));
  spans[3] = (size_t)p->kv_length * sizeof(uint16_t);
  CHECK(matrix_span(row * 2u, p->query_heads, p->output_head_stride,
                    1u, 0u, &spans[4]));
  const size_t batch_strides[] = {p->q_batch_stride, p->k_batch_stride,
      p->v_batch_stride, p->mask_batch_stride, p->output_batch_stride};
  const size_t capacities[] = {p->query_bytes, p->key_bytes, p->value_bytes,
                              p->mask_bytes, p->output_bytes};
  const uintptr_t bases[] = {(uintptr_t)p->query, (uintptr_t)p->key,
      (uintptr_t)p->value, (uintptr_t)p->mask, (uintptr_t)p->output};
  uintptr_t lasts[5];
  for (unsigned i = 0; i < 5; ++i) {
    if (!(i == 3u && p->mask_batch_stride == 0u))
      CHECK(batch_span(spans[i], p->batches, batch_strides[i], &spans[i]));
    if (!bases[i] || capacities[i] < spans[i] ||
        __builtin_add_overflow(bases[i], spans[i] - 1u, &lasts[i]))
      return AKV_STATUS_RANGE;
  }
  for (unsigned i = 0; i < 4; ++i)
    if (bases[4] <= lasts[i] && bases[i] <= lasts[4]) return AKV_STATUS_ALIAS;

  const uint32_t gqa = p->query_heads / p->kv_heads;
  uint64_t count = 0;
  akv_attention_plan_t plan;
  /* Validate all groups before the first callback; no speculative issue. */
  for (uint32_t b = 0; b < p->batches; ++b)
    for (uint32_t h = 0; h < p->query_heads;) {
      uint32_t rows = gqa - h % gqa;
      if (rows > limit) rows = limit;
      CHECK(group_plan(device, p, b, h, rows, &plan));
      if (count == UINT64_MAX) return AKV_STATUS_RANGE;
      ++count;
      h += rows;
    }
#undef CHECK
  if (group_count) *group_count = count;
  return AKV_STATUS_OK;
}

akv_status_t akv_decode_execute(const akv_device_t *device,
                                const akv_decode_problem_t *p,
                                akv_decode_group_executor_t executor,
                                void *context, uint64_t *completed_groups) {
  if (completed_groups) *completed_groups = 0;
  if (!p || !device || !executor) return AKV_STATUS_BAD_ARGUMENT;
  const akv_decode_problem_t problem = *p;
  const akv_device_t selected_device = *device;
  p = &problem;
  device = &selected_device;
  const akv_status_t status = akv_decode_validate(device, p, NULL);
  if (status != AKV_STATUS_OK) return status;
  const uint32_t limit = device->capabilities.max_q_rows;
  const uint32_t gqa = p->query_heads / p->kv_heads;
  uint64_t complete = 0;
  akv_attention_plan_t plan;
  for (uint32_t b = 0; b < p->batches; ++b)
    for (uint32_t h = 0; h < p->query_heads;) {
      uint32_t rows = gqa - h % gqa;
      if (rows > limit) rows = limit;
      if (group_plan(device, p, b, h, rows, &plan) != AKV_STATUS_OK ||
          executor(context, &plan, b, h) != AKV_STATUS_OK)
        return AKV_STATUS_EXECUTION;
      ++complete;
      if (completed_groups) *completed_groups = complete;
      h += rows;
    }
  return AKV_STATUS_OK;
}
