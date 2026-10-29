#ifndef PREFILL_VALUE_CACHE_CANDIDATE_H
#define PREFILL_VALUE_CACHE_CANDIDATE_H

#include <stdint.h>
#include <string.h>

/* Experimental, not connected to production. Reset before each KV head and
 * each invocation. Inputs must remain immutable. The decode callback must be
 * deterministic, have no externally visible side effects or FP exceptions,
 * return zero on success, and write all dim elements on success. Generic
 * native bindings do NOT promise this contract and must not use this wrapper.
 * Output must be disjoint from the cache. Vector configuration is caller-clobbered. */
enum { PREFILL_VCACHE_TOKENS = 32, PREFILL_VCACHE_DIM = 256 };
typedef struct {
  uint32_t valid;
  unsigned dim;
  float values[PREFILL_VCACHE_TOKENS][PREFILL_VCACHE_DIM];
} prefill_value_cache_t;
typedef int (*prefill_value_decode_t)(void *, unsigned, float *, unsigned);

static inline int prefill_value_cache_reset(prefill_value_cache_t *cache, unsigned dim) {
  if (!cache) return -1;
  cache->valid = 0;
  cache->dim = dim && dim <= PREFILL_VCACHE_DIM ? dim : 0;
  return cache->dim ? 0 : -1;
}

static inline int prefill_value_cache_get(prefill_value_cache_t *cache,
    prefill_value_decode_t decode, void *context, unsigned token,
    float *output, unsigned dim) {
  if (!cache || !decode || !output || !dim || dim != cache->dim) return -1;
  if (token >= PREFILL_VCACHE_TOKENS) return decode(context, token, output, dim);
  const uint32_t bit = UINT32_C(1) << token;
  if (!(cache->valid & bit)) {
    const int status = decode(context, token, output, dim);
    if (status) return status;
    memcpy(cache->values[token], output, dim * sizeof(float));
    cache->valid |= bit;
  } else {
    memcpy(output, cache->values[token], dim * sizeof(float));
  }
  return 0;
}
#endif
