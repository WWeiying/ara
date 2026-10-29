#include <assert.h>
#include <stdio.h>
#include "value_cache_candidate.h"

static prefill_value_cache_t cache;
typedef struct { unsigned calls, head, fail; } context_t;

static uint32_t expected(unsigned head, unsigned token, unsigned element) {
  /* Include signed zero and arbitrary bit patterns: cache transport is exact. */
  if (element == 0) return UINT32_C(0x80000000);
  return head * UINT32_C(0x1020304) ^ token * UINT32_C(0x1234567) ^ element;
}

static int decode(void *opaque, unsigned token, float *out, unsigned dim) {
  context_t *c = opaque;
  ++c->calls;
  for (unsigned d = 0; d < dim; ++d) {
    uint32_t bits = expected(c->head, token, d);
    memcpy(out + d, &bits, sizeof(bits));
    if (c->fail) return 7;
  }
  return 0;
}

int main(void) {
  float out[256];
  unsigned checks = 0;
  for (unsigned dim = 32; dim <= 256; dim += 32) {
    for (unsigned head = 0; head < 3; ++head) {
      context_t ctx = {0, head, 0};
      assert(!prefill_value_cache_reset(&cache, dim));
      const unsigned limits[] = {4, 8, 65, 1, 33, 32, 20};
      unsigned calls = 0;
      uint32_t seen = 0;
      for (unsigned group = 0; group < sizeof(limits)/sizeof(*limits); ++group) {
        for (unsigned token = 0; token < limits[group]; ++token) {
          if (token >= 32 || !(seen & (UINT32_C(1) << token))) ++calls;
          if (token < 32) seen |= UINT32_C(1) << token;
          memset(out, 0xa5, sizeof(out));
          assert(!prefill_value_cache_get(&cache, decode, &ctx, token, out, dim));
          assert(ctx.calls == calls);
          for (unsigned d = 0; d < 256; ++d) {
            uint32_t bits;
            memcpy(&bits, out + d, sizeof(bits));
            assert(bits == (d < dim ? expected(head, token, d) : UINT32_C(0xa5a5a5a5)));
          }
          ++checks;
        }
      }
    }
  }
  context_t ctx = {0, 9, 1};
  assert(!prefill_value_cache_reset(&cache, 128));
  assert(prefill_value_cache_get(&cache, decode, &ctx, 31, out, 128) == 7);
  assert(cache.valid == 0);
  ctx.fail = 0;
  assert(!prefill_value_cache_get(&cache, decode, &ctx, 31, out, 128));
  assert(ctx.calls == 2 && cache.valid == UINT32_C(0x80000000));
  assert(prefill_value_cache_get(&cache, decode, &ctx, 31, out, 64) == -1);
  assert(prefill_value_cache_reset(&cache, 257) == -1 && !cache.valid);
  assert(prefill_value_cache_get(&cache, decode, &ctx, 0, out, 0) == -1);
  printf("VALUE_CACHE_PASS checks=%u dims=8 kv_heads=3 failed_fill_retry=1\n", checks);
  return 0;
}
