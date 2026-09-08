#include "../src/akv_online_internal.h"

#include <assert.h>
#include <stdio.h>

static void compare(unsigned length, unsigned tile, int masked, int sink) {
  float scores[140], values[140], weights[64], scales[64];
  float maximum = sink ? 0.375f : -INFINITY;
  float expected_maximum = maximum;
  float sum = sink ? 1.0f : 0.0f, expected_sum = sum;
  /* Host checks scheduling; the native smoke checks every F16 rounding. */
  float accumulator = 0.0f, expected = 0.0f;
  for (unsigned t = 0; t < length; ++t) {
    scores[t] = (float)((int)((t * 13u) % 29u) - 17) * 0.0625f;
    if (t == 63u || t == 64u || t == 139u)
      scores[t] = 1.0f + (float)t * 0.00390625f;
    if (masked == 2 || (masked && (t < 3u || t % 11u == 0u)))
      scores[t] = -INFINITY;
    values[t] = (int)(t % 17u) - 8.125f;
    if (scores[t] == -INFINITY) continue;
    float rescale = 1.0f, weight = 1.0f;
    if (scores[t] > expected_maximum) {
      rescale = expf(expected_maximum - scores[t]);
      expected_maximum = scores[t];
      expected *= rescale;
    } else {
      weight = expf(scores[t] - expected_maximum);
    }
    expected = fmaf(values[t], weight, expected);
    volatile float scaled = expected_sum * rescale;
    expected_sum = scaled + weight;
  }
  for (unsigned first = 0; first < length; first += tile) {
    const unsigned count = length - first < tile ? length - first : tile;
    memcpy(weights, scores + first, count * sizeof(float));
    akv_online_prepare_exponents(weights, scales, count, &maximum);
    for (unsigned t = 0; t < count; ++t) {
      weights[t] = expf(weights[t]);
      if (scales[t] != 1.0f)
        accumulator *= scales[t];
      if (weights[t] != 0.0f)
        accumulator = fmaf(values[first + t], weights[t], accumulator);
    }
    sum = akv_online_update_sum(sum, weights, scales, count);
  }
  assert(memcmp(&accumulator, &expected, sizeof(expected)) == 0);
  assert(sum == expected_sum);
  assert(maximum == expected_maximum);
}

int main(void) {
  const unsigned lengths[] = {1, 3, 17, 64, 65, 140};
  const unsigned tiles[] = {1, 7, 64};
  unsigned cases = 0;
  for (unsigned n = 0; n < sizeof(lengths) / sizeof(lengths[0]); ++n)
    for (unsigned t = 0; t < sizeof(tiles) / sizeof(tiles[0]); ++t)
      for (int masked = 0; masked < 3; ++masked)
        for (int sink = 0; sink < 2; ++sink) {
          compare(lengths[n], tiles[t], masked, sink);
          ++cases;
        }
  printf("AKV online schedule: PASS cases=%u\n", cases);
  return 0;
}
