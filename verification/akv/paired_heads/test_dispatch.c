#include "../../../software/akv/experimental/paired_heads/dispatch.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static uint16_t query[8 * 160], accumulator[8 * 256];
static float score[8 * 64], scale[8];
static unsigned calls, cursor, expected_heads, expected_dim, expected_tokens;
static size_t expected_stride;
static int expected_pair;

static void record(unsigned heads, int paired, const void *q, const void *s,
                   const void *a, const void *sc, unsigned tokens,
                   size_t stride, unsigned dim) {
  assert(tokens == expected_tokens && dim == expected_dim);
  assert(stride == expected_stride);
  assert(paired == (expected_pair && cursor + 1 < expected_heads));
  assert(heads == (paired ? 2u : expected_pair ? 1u : expected_heads));
  assert(cursor + heads <= expected_heads);
  if (q)
    assert(q == (const char *)query + cursor * expected_stride);
  assert(s == score + cursor * 64);
  if (a) assert(a == accumulator + cursor * 256);
  if (sc) assert(sc == scale + cursor);
  cursor += heads;
  ++calls;
}

void akv_v2_compute_scores_f16_generic(const uint16_t *q, float *s,
    uint32_t tokens, size_t stride, uint32_t heads, uint32_t dim) {
  record(heads, 0, q, s, NULL, NULL, tokens, stride, dim);
}
void akv_experimental_qk_f16_pair_panel4(const uint16_t *q, float *s,
    uint32_t tokens, size_t stride, uint32_t dim) {
  record(2, 1, q, s, NULL, NULL, tokens, stride, dim);
}
void akv_v2_update_outputs_f16_generic(const float *s, uint16_t *a,
    const float *sc, uint32_t tokens, uint32_t heads, uint32_t dim) {
  record(heads, 0, NULL, s, a, sc, tokens, expected_stride, dim);
}
void akv_experimental_pv_f16_pair(const float *s, uint16_t *a,
    const float *sc, uint32_t tokens, uint32_t dim) {
  record(2, 1, NULL, s, a, sc, tokens, expected_stride, dim);
}

int main(void) {
  const unsigned dims[] = {64, 96, 128};
  const size_t strides[] = {256, 258, 288, 320};
  unsigned schedules = 0;
  memset(query, 0xa5, sizeof(query));
  memset(score, 0xa5, sizeof(score));
  memset(accumulator, 0xa5, sizeof(accumulator));
  memset(scale, 0xa5, sizeof(scale));
  for (unsigned d = 0; d < 3; ++d)
    for (unsigned st = 0; st < 4; ++st)
      for (expected_heads = 1; expected_heads <= 8; ++expected_heads)
        for (expected_tokens = 1; expected_tokens <= 64; ++expected_tokens)
          for (expected_pair = 0; expected_pair <= 1; ++expected_pair) {
            expected_dim = dims[d];
            expected_stride = strides[st];
            calls = cursor = 0;
            akv_pair_qk_f16_dispatch(expected_pair, query, score,
                expected_tokens, expected_stride, expected_heads, expected_dim);
            assert(cursor == expected_heads);
            assert(calls == (expected_pair ? (expected_heads + 1) / 2 : 1));
            calls = cursor = 0;
            akv_pair_pv_f16_dispatch(expected_pair, score, accumulator, scale,
                expected_tokens, expected_heads, expected_dim);
            assert(cursor == expected_heads);
            assert(calls == (expected_pair ? (expected_heads + 1) / 2 : 1));
            schedules += 2;
          }
  /* The test stubs must not write numerical data or fake a leaf execution. */
#define UNCHANGED(array) do { \
    const unsigned char *p = (const unsigned char *)(array); \
    for (size_t i = 0; i < sizeof(array); ++i) assert(p[i] == 0xa5); \
  } while (0)
  UNCHANGED(query); UNCHANGED(score); UNCHANGED(accumulator); UNCHANGED(scale);
#undef UNCHANGED
  printf("PAIR_DISPATCH_PASS schedules=%u numerical_execution=0\n", schedules);
  return 0;
}
