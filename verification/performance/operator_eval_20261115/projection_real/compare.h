#ifndef OPERATOR_FORMAT_COMPARE_H
#define OPERATOR_FORMAT_COMPARE_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <math.h>

typedef struct {
  uint32_t count, mismatches, first, expected_hash, actual_hash;
  uint32_t raw_differences, first_actual, first_expected;
} format_comparison;

static inline uint32_t format_hash(const void *data, size_t n) {
  const unsigned char *p = data;
  uint32_t h = UINT32_C(2166136261);
  for (size_t i = 0; i < n; ++i) h = (h ^ p[i]) * UINT32_C(16777619);
  return h;
}
static inline uint32_t format_bits(float f) {
  uint32_t u; memcpy(&u, &f, sizeof(u)); return u;
}
static inline format_comparison format_compare(const void *actual, const void *expected,
    uint32_t count, int floats, int tolerant, float atol, float rtol) {
  format_comparison c = {.count=count, .first=UINT32_MAX};
  const unsigned char *a = actual, *e = expected;
  c.actual_hash = format_hash(a, (size_t)count*(floats ? 4 : 1));
  c.expected_hash = format_hash(e, (size_t)count*(floats ? 4 : 1));
  for (uint32_t i = 0; i < count; ++i) {
    uint32_t av = a[i], ev = e[i];
    int bad;
    if (floats) {
      float af, ef;
      memcpy(&av, a+4*i, 4); memcpy(&ev, e+4*i, 4);
      memcpy(&af, &av, 4); memcpy(&ef, &ev, 4);
      bad = !isfinite(af) || !isfinite(ef) ||
        (tolerant ? fabsf(af-ef) > atol+rtol*fabsf(ef) : av != ev);
    } else bad = av != ev;
    c.raw_differences += av != ev;
    if (bad) {
      if (!c.mismatches) { c.first=i; c.first_actual=av; c.first_expected=ev; }
      ++c.mismatches;
    }
  }
  return c;
}
#endif
