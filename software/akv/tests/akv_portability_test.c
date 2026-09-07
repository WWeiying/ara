#include "akv/akv_decode.h"
#include "akv/akv_features.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
  const akv_decode_problem_t *problem;
  unsigned calls, fail_at;
} recorder_t;

static akv_status_t execute_group(void *opaque, const akv_attention_plan_t *plan,
                                  uint32_t batch, uint32_t first) {
  recorder_t *r = opaque;
  const akv_decode_problem_t *p = r->problem;
  const uint32_t kh = first / (p->query_heads / p->kv_heads);
  assert(plan->descriptor.q_base == (uintptr_t)p->query +
      batch * p->q_batch_stride + first * p->q_head_stride);
  assert(plan->descriptor.k_base == (uintptr_t)p->key +
      batch * p->k_batch_stride + kh * p->k_head_stride);
  assert(plan->output == (float *)((char *)p->output +
      batch * p->output_batch_stride + first * p->output_head_stride));
  ++r->calls;
  if (r->fail_at == r->calls) return AKV_STATUS_CAPABILITY;
  return akv_attention_execute_v2_with_features_reference(plan, NULL);
}

static void *buffer(size_t bytes) {
  void *p = aligned_alloc(64u, (bytes + 63u) & ~(size_t)63u);
  assert(p);
  memset(p, 0, bytes);
  return p;
}

static void test_decode(unsigned gqa, unsigned dim, unsigned tokens,
                         int token_major, int broadcast_mask) {
  const size_t row = (size_t)dim * 2u;
  akv_decode_problem_t p = {
      .batches = 2, .query_heads = 2 * gqa, .kv_heads = 2,
      .kv_length = tokens, .head_dim = dim, .scale = 0.125f,
      .q_head_stride = row + 32,
      .k_token_stride = token_major ? (row + 32) * 2 : row + 32,
      .k_head_stride = token_major ? row + 32 : (row + 32) * tokens,
      .v_token_stride = row + 64, .v_head_stride = (row + 64) * tokens,
      .output_head_stride = row * 2 + 16,
      .mask_batch_stride = broadcast_mask ? 0 : (tokens + 16) * 2u,
  };
  p.q_batch_stride = p.q_head_stride * p.query_heads + 64;
  p.k_batch_stride = (row + 32) * tokens * 2 + 64;
  p.v_batch_stride = p.v_head_stride * 2 + 64;
  p.output_batch_stride = p.output_head_stride * p.query_heads + 64;
  p.query_bytes = p.q_batch_stride * p.batches;
  p.key_bytes = p.k_batch_stride * p.batches;
  p.value_bytes = p.v_batch_stride * p.batches;
  p.mask_bytes = broadcast_mask ? tokens * 2u : p.mask_batch_stride * p.batches;
  p.output_bytes = p.output_batch_stride * p.batches;
  p.query = buffer(p.query_bytes); p.key = buffer(p.key_bytes);
  p.value = buffer(p.value_bytes); p.mask = buffer(p.mask_bytes);
  p.output = buffer(p.output_bytes);
  for (unsigned b = 0; b < p.batches; ++b)
    for (unsigned kh = 0; kh < p.kv_heads; ++kh)
      for (unsigned t = 0; t < tokens; ++t) {
        uint16_t *v = (uint16_t *)((char *)p.value +
            b * p.v_batch_stride + kh * p.v_head_stride + t * p.v_token_stride);
        for (unsigned d = 0; d < dim; ++d) v[d] = (uint16_t)(0x3c00 + (b * 2 + kh) * 0x400);
      }
  akv_device_t device;
  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);
  uint64_t count = 0, completed = 0;
  const uint64_t expected = 4u * ((gqa + 7u) / 8u);
  assert(akv_decode_validate(&device, &p, &count) == AKV_STATUS_OK);
  assert(count == expected);
  recorder_t r = {.problem = &p};
  assert(akv_decode_execute(&device, &p, execute_group, &r, &completed) == AKV_STATUS_OK);
  assert(r.calls == expected && completed == expected);
  for (unsigned b = 0; b < p.batches; ++b)
    for (unsigned h = 0; h < p.query_heads; ++h) {
      const float *o = (const float *)((const char *)p.output +
          b * p.output_batch_stride + h * p.output_head_stride);
      for (unsigned d = 0; d < dim; ++d)
        assert(o[d] == (float)(1u << (b * 2u + h / gqa)));
    }

  akv_decode_problem_t bad = p;
  bad.output_bytes = 4;
  r.calls = 0;
  assert(akv_decode_execute(&device, &bad, execute_group, &r, NULL) == AKV_STATUS_RANGE);
  assert(r.calls == 0);
  bad = p;
  bad.output = (float *)((char *)p.query + p.q_batch_stride);
  assert(akv_decode_validate(&device, &bad, NULL) == AKV_STATUS_ALIAS);
  bad = p; bad.k_batch_stride = 32;
  assert(akv_decode_validate(&device, &bad, NULL) == AKV_STATUS_LAYOUT);
  bad = p; bad.k_head_stride = SIZE_MAX;
  assert(akv_decode_validate(&device, &bad, NULL) == AKV_STATUS_RANGE);
  bad = p; bad.kv_heads = 0;
  assert(akv_decode_validate(&device, &bad, NULL) == AKV_STATUS_SHAPE);
  r.calls = 0; r.fail_at = 2;
  assert(akv_decode_execute(&device, &p, execute_group, &r, &completed) == AKV_STATUS_EXECUTION);
  assert(r.calls == 2 && completed == 1);
  free((void *)p.query); free((void *)p.key); free((void *)p.value);
  free((void *)p.mask); free(p.output);
}

static void test_features(void) {
  uint16_t plain_mask[2] = {0};
  akv_attention_features_t empty = {0};
  assert(akv_attention_can_use_plain_scores(&empty, plain_mask, 2));
  assert(akv_attention_can_use_plain_scores(NULL, plain_mask, 2));
  assert(!akv_attention_can_use_plain_scores(&empty, NULL, 2));
  assert(!akv_attention_can_use_plain_scores(&empty, plain_mask, 0));
  plain_mask[0] = 0xfc00;
  assert(!akv_attention_can_use_plain_scores(&empty, plain_mask, 2));
  plain_mask[0] = 0xb400;
  assert(!akv_attention_can_use_plain_scores(&empty, plain_mask, 2));
  plain_mask[0] = 0;
  empty.softcap = 1;
  assert(!akv_attention_can_use_plain_scores(&empty, plain_mask, 2));
  empty.softcap = 0; empty.mask_scale_enabled = 1;
  assert(!akv_attention_can_use_plain_scores(&empty, plain_mask, 2));
  empty.mask_scale_enabled = 0; empty.position_bias_enabled = 1;
  assert(!akv_attention_can_use_plain_scores(&empty, plain_mask, 2));
  empty.position_bias_enabled = 0; empty.sinks_enabled = 1;
  assert(!akv_attention_can_use_plain_scores(&empty, plain_mask, 2));
  empty.sinks_enabled = 0; empty.window_enabled = 1;
  assert(!akv_attention_can_use_plain_scores(&empty, plain_mask, 2));
  akv_attention_features_t f = {
      .softcap = 2.0f, .mask_scale_enabled = 1, .position_bias_enabled = 1,
      .mask_scale = {0.5f}, .position_slope = {0.25f},
      .key_position_base = 100, .query_position = 103,
  };
  assert(akv_attention_features_validate(&f, 1, 5) == AKV_STATUS_OK);
  float actual = akv_attention_score_transform(4, 0.5f, 0xbc00, 0, 1, &f);
  assert(fabsf(actual - (2 * tanhf(1) - 0.5f - 0.5f)) < 1e-6f);
  assert(akv_attention_score_transform(INFINITY, 1, 0xfc00, 0, 0, &f) == -INFINITY);
  f.window_enabled = 1; f.window_left = 1; f.window_right = 0;
  assert(akv_attention_score_transform(0, 1, 0, 0, 1, &f) == -INFINITY);
  assert(isfinite(akv_attention_score_transform(0, 1, 0, 0, 2, &f)));
  assert(isfinite(akv_attention_score_transform(0, 1, 0, 0, 3, &f)));
  assert(akv_attention_score_transform(0, 1, 0, 0, 4, &f) == -INFINITY);
  f.key_position_base = UINT64_MAX;
  assert(akv_attention_features_validate(&f, 1, 2) == AKV_STATUS_BAD_ARGUMENT);
  f.key_position_base = 0; f.softcap = NAN;
  assert(akv_attention_features_validate(&f, 1, 2) == AKV_STATUS_BAD_ARGUMENT);

  uint16_t q[64] __attribute__((aligned(64))) = {0};
  uint16_t k[65][64] __attribute__((aligned(64))) = {{0}};
  uint16_t v[65][64] __attribute__((aligned(64))) = {{0}};
  uint16_t mask[65] = {0};
  float output[64];
  for (unsigned t = 0; t < 65; ++t) {
    mask[t] = t < 64 ? 0xfc00 : 0;
    for (unsigned d = 0; d < 64; ++d) v[t][d] = 0x4000;
  }
  akv_attention_problem_t p = {
      .query = q, .key = &k[0][0], .value = &v[0][0], .mask = mask,
      .output = output, .q_row_stride_bytes = 128, .k_token_stride_bytes = 128,
      .v_token_stride_bytes = 128, .output_row_stride_bytes = 256,
      .q_rows = 1, .head_dim = 64, .kv_length = 65, .scale = 0.125f,
  };
  akv_device_t device;
  akv_attention_plan_t plan;
  assert(akv_device_init_reference(&device) == AKV_STATUS_OK);
  assert(akv_attention_plan_create_v2(&device, &p, &plan) == AKV_STATUS_OK);
  memset(&f, 0, sizeof(f));
  f.sinks_enabled = 1; f.sinks[0] = 0;
  assert(akv_attention_execute_v2_with_features_reference(&plan, &f) == AKV_STATUS_OK);
  for (unsigned d = 0; d < 64; ++d) assert(output[d] == 1.0f);
  mask[64] = 0xfc00;
  assert(akv_attention_execute_v2_with_features_reference(&plan, NULL) == AKV_STATUS_OK);
  for (unsigned d = 0; d < 64; ++d) assert(output[d] == 0.0f);
  mask[0] = 0x7e00;
  assert(akv_attention_execute_v2_with_features_reference(&plan, NULL) == AKV_STATUS_BAD_ARGUMENT);
}

int main(void) {
  const unsigned gqas[] = {1, 3, 6, 8, 9, 17};
  const unsigned dims[] = {64, 96, 128, 256};
  const unsigned tokens[] = {1, 63, 64, 65};
  unsigned cases = 0;
  for (unsigned g = 0; g < 6; ++g)
    for (unsigned d = 0; d < 4; ++d)
      for (unsigned t = 0; t < 4; ++t)
        for (int layout = 0; layout < 2; ++layout) {
          test_decode(gqas[g], dims[d], tokens[t], layout, t & 1);
          ++cases;
        }
  test_features();
  printf("AKV portable Decode: %u batched/layout/tail cases + score features PASS\n", cases);
  return 0;
}
