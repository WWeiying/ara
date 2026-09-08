#ifndef AKV_ONLINE_INTERNAL_H
#define AKV_ONLINE_INTERNAL_H

#include <math.h>
#include <stdint.h>
#include <string.h>

/* Keep token-order maximum updates even when QK and exp run in a tile. */
static inline void akv_online_prepare_exponents(
    float *scores, float *rescale, uint32_t tokens, float *running_maximum) {
  float maximum = *running_maximum;
  for (uint32_t token = 0; token < tokens; ++token) {
    const float score = scores[token];
    uint32_t bits;
    memcpy(&bits, &score, sizeof(bits));
    rescale[token] = 1.0f;
    if (bits == UINT32_C(0xff800000))
      continue; /* Keep -Inf for exp; do not evaluate -Inf - -Inf. */
    if (score > maximum) {
      rescale[token] = expf(maximum - score);
      maximum = score;
    }
    scores[token] = score - maximum;
  }
  *running_maximum = maximum;
}

static inline float akv_online_update_sum(
    float sum, const float *weights, const float *rescale, uint32_t tokens) {
  for (uint32_t token = 0; token < tokens; ++token) {
    /* Separate F32 rounding, not a contracted FMA or a tile reduction. */
    volatile float scaled = sum * rescale[token];
    sum = scaled + weights[token];
  }
  return sum;
}

#endif
