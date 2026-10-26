#include "kernel.h"

/* Also serves as a compile-only RVV probe without a host/libc test runner. */
__attribute__((noinline)) int grouped_pv_probe(unsigned heads, unsigned dim,
    size_t stride, float *out, const float *v, const float *ms,
    const float *vs, unsigned mask) {
  return akv_grouped_pv_update(heads, dim, stride, out, v, ms, vs, mask);
}

#ifndef GROUPED_PV_COMPILE_ONLY
#include <fenv.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { GUARD = 8, STRIDE = 273, COUNT = 8 * STRIDE + 2 * GUARD };
static unsigned cases, rejected;

#define REQUIRE(x) do { if (!(x)) { \
  fprintf(stderr, "FAIL line=%d case=%u: %s\n", __LINE__, cases, #x); \
  exit(1); \
} } while (0)

static float from_bits(uint32_t bits) {
  float x;
  memcpy(&x, &bits, sizeof(x));
  return x;
}

typedef struct { int flags, rounding; unsigned long fcsr, vcsr; } fp_state;

static fp_state snapshot(void) {
  fp_state s = {0, 0, 0, 0};
#if defined(__riscv_vector)
  __asm__ volatile ("csrr %0, fcsr\n\tcsrr %1, vcsr"
                    : "=r"(s.fcsr), "=r"(s.vcsr) :: "memory");
#endif
  s.flags = fetestexcept(FE_ALL_EXCEPT);
  s.rounding = fegetround();
  return s;
}

static void reset_fp(int sticky) {
  REQUIRE(fesetround(FE_TONEAREST) == 0);
  REQUIRE(feclearexcept(FE_ALL_EXCEPT) == 0);
  if (sticky) REQUIRE(feraiseexcept(FE_DIVBYZERO) == 0);
#if defined(__riscv_vector)
  __asm__ volatile ("csrwi vcsr, 5" ::: "memory");
#endif
}

static void same_fp(fp_state a, fp_state b) {
  REQUIRE(a.flags == b.flags && a.rounding == b.rounding);
  REQUIRE(a.rounding == FE_TONEAREST);
#if defined(__riscv_vector)
  REQUIRE(a.fcsr == b.fcsr && a.vcsr == 5 && b.vcsr == 5);
#endif
}

/* Independent old order: an entire head's scale pass, then its MAD pass.
 * Compile this translation unit with -fno-tree-vectorize. */
__attribute__((noinline)) static void reference(unsigned heads, unsigned dim,
    size_t stride, float *out, const float *v, const float *ms,
    const float *vs, unsigned mask) {
  for (unsigned h = 0; h < heads; ++h) {
    if (mask & (1u << h)) {
      for (unsigned d = 0; d < dim; ++d) {
        volatile float scaled = out[h * stride + d] * ms[h];
        out[h * stride + d] = scaled;
      }
    }
    for (unsigned d = 0; d < dim; ++d)
      out[h * stride + d] = fmaf(v[d], vs[h], out[h * stride + d]);
  }
}

static int one_case(unsigned heads, unsigned dim, size_t stride,
                    unsigned mask, unsigned pattern, int sticky) {
  float actual[COUNT], expected[COUNT], before[COUNT];
  float value[256 + 2 * GUARD], vcopy[256 + 2 * GUARD];
  float ms[8 + 2 * GUARD], vs[8 + 2 * GUARD];
  float mcopy[8 + 2 * GUARD], scopy[8 + 2 * GUARD];
  const uint32_t pool[] = {0, 0x80000000u, 1, 0x80000001u,
    0x007fffffu, 0x00800000u, 0x80800000u, 0x3f000000u,
    0xbf000000u, 0x3f800001u, 0xbf800001u, 0x40000000u};
  for (unsigned i = 0; i < COUNT; ++i) actual[i] = from_bits(0x4a55aa55u);
  for (unsigned i = 0; i < 256 + 2 * GUARD; ++i)
    value[i] = from_bits(0x4b123456u);
  for (unsigned i = 0; i < 8 + 2 * GUARD; ++i)
    ms[i] = vs[i] = from_bits(0x4c345678u);
  for (unsigned d = 0; d < dim; ++d) {
    value[GUARD + d] = from_bits(pool[(d * 5 + pattern) % 12]);
    for (unsigned h = 0; h < heads; ++h)
      actual[GUARD + h * stride + d] = from_bits(pool[(d + 3 * h + pattern) % 12]);
  }
  for (unsigned h = 0; h < heads; ++h) {
    ms[GUARD + h] = from_bits(pool[(h + pattern + 7) % 12]);
    vs[GUARD + h] = from_bits(pool[(2 * h + pattern + 7) % 12]);
    if (pattern == 1) { /* Exact zeros, including negative zero coefficients. */
      ms[GUARD + h] = -0.0f;
      vs[GUARD + h] = -0.0f;
    }
    if (pattern == 2) { /* Inexact tiny scale must round before the FMA. */
      ms[GUARD + h] = 0.1f;
      vs[GUARD + h] = 0.0f;
      for (unsigned d = 0; d < dim; ++d)
        actual[GUARD + h * stride + d] = FLT_MIN;
    }
    if (pattern == 3) { /* Scalar product rounding versus contraction. */
      ms[GUARD + h] = from_bits(0x3f800001u);
      vs[GUARD + h] = -1.0f;
      for (unsigned d = 0; d < dim; ++d) {
        actual[GUARD + h * stride + d] = from_bits(0x3f7fffffu);
        value[GUARD + d] = 1.0f;
      }
    }
    if (pattern == 4) { /* Mask-zero coefficients must not be evaluated. */
      ms[GUARD + h] = (mask & (1u << h)) ? 0.5f : from_bits(0x7f800001u);
      vs[GUARD + h] = 1.0f;
      for (unsigned d = 0; d < dim; ++d) {
        actual[GUARD + h * stride + d] = 1.0f;
        value[GUARD + d] = 1.0f;
      }
    }
    if (pattern == 5) { /* Overflow is observable even with a zero MAD weight. */
      ms[GUARD + h] = 2.0f;
      vs[GUARD + h] = 0.0f;
      for (unsigned d = 0; d < dim; ++d) {
        actual[GUARD + h * stride + d] = FLT_MAX;
        value[GUARD + d] = 1.0f;
      }
    }
  }
  memcpy(before, actual, sizeof(actual));
  memcpy(expected, actual, sizeof(actual));
  memcpy(vcopy, value, sizeof(value));
  memcpy(mcopy, ms, sizeof(ms));
  memcpy(scopy, vs, sizeof(vs));
  reset_fp(sticky);
  reference(heads, dim, stride, expected + GUARD, value + GUARD,
            ms + GUARD, vs + GUARD, mask);
  const fp_state ref = snapshot();
  reset_fp(sticky);
  int rc = grouped_pv_probe(heads, dim, stride, actual + GUARD, value + GUARD,
                           ms + GUARD, vs + GUARD, mask);
  const fp_state got = snapshot();
  REQUIRE(rc == AKV_GROUPED_PV_OK);
  same_fp(ref, got);
  REQUIRE(memcmp(actual, expected, sizeof(actual)) == 0);
  REQUIRE(memcmp(value, vcopy, sizeof(value)) == 0);
  REQUIRE(memcmp(ms, mcopy, sizeof(ms)) == 0);
  REQUIRE(memcmp(vs, scopy, sizeof(vs)) == 0);
  for (unsigned i = 0; i < COUNT; ++i) {
    int active = 0;
    for (unsigned h = 0; h < heads; ++h)
      if (i >= GUARD + h * stride && i < GUARD + h * stride + dim) active = 1;
    if (!active) REQUIRE(memcmp(actual + i, before + i, sizeof(float)) == 0);
  }
  if (pattern == 2 && mask)
    REQUIRE((got.flags & (FE_UNDERFLOW | FE_INEXACT)) == (FE_UNDERFLOW | FE_INEXACT));
  if (pattern == 4) REQUIRE(!(got.flags & FE_INVALID));
  if (pattern == 5 && mask)
    REQUIRE((got.flags & (FE_OVERFLOW | FE_INEXACT)) == (FE_OVERFLOW | FE_INEXACT));
  ++cases;
  return got.flags;
}

static void invalid_cases(void) {
  float out[COUNT], copy[COUNT], v[256] = {0}, ms[8] = {0}, vs[8] = {0};
  memset(out, 0x5a, sizeof(out));
  memcpy(copy, out, sizeof(out));
  for (unsigned which = 0; which < 17; ++which) {
    unsigned h = 2, d = 32, mask = 0;
    size_t stride = 40;
    float *y = out;
    const float *vv = v, *mm = ms, *ss = vs;
    switch (which) {
      case 0: h = 0; break;
      case 1: h = 9; break;
      case 2: d = 31; break;
      case 3: d = 257; break;
      case 4: stride = 31; break;
      case 5: mask = 4; break;
      case 6: stride = SIZE_MAX; break;
      case 7: y = NULL; break;
      case 8: vv = NULL; break;
      case 9: mm = NULL; break;
      case 10: ss = NULL; break;
      case 11: vv = out; break;
      case 12: mm = out + 35; break; /* Padding is in the output span. */
      case 13: ss = out + 40; break;
      case 14: y = (float *)((unsigned char *)out + 1); break;
      case 15: vv = (const float *)(UINTPTR_MAX - 3); break;
      case 16: h = 32; break; /* Must not shift by an unchecked width. */
    }
    reset_fp(1);
    fp_state before = snapshot();
    int rc = grouped_pv_probe(h, d, stride, y, vv, mm, ss, mask);
    fp_state after = snapshot();
    REQUIRE(rc == AKV_GROUPED_PV_BAD_ARGUMENT);
    same_fp(before, after);
    REQUIRE(memcmp(out, copy, sizeof(out)) == 0);
    ++rejected;
  }
}

int main(void) {
  fenv_t saved;
  REQUIRE(fegetenv(&saved) == 0);
#if defined(__riscv_vector)
  unsigned long saved_vcsr;
  __asm__ volatile ("csrr %0, vcsr" : "=r"(saved_vcsr));
#endif
  const unsigned dims[] = {32, 33, 63, 64, 96, 127, 128, 160, 192, 224, 255, 256};
  const unsigned pads[] = {0, 1, 17};
  for (unsigned h = 1; h <= 8; ++h)
    for (unsigned di = 0; di < sizeof(dims) / sizeof(dims[0]); ++di)
      for (unsigned pi = 0; pi < sizeof(pads) / sizeof(pads[0]); ++pi)
        for (unsigned mi = 0; mi < 4; ++mi)
          for (unsigned pattern = 0; pattern < 6; ++pattern)
            for (int sticky = 0; sticky <= 1; ++sticky) {
              unsigned all = (1u << h) - 1;
              unsigned mask = mi == 0 ? 0 : mi == 1 ? all :
                              mi == 2 ? all & 0x55u : 1u << (h - 1);
              one_case(h, dims[di], dims[di] + pads[pi], mask, pattern, sticky);
            }
  invalid_cases();
  REQUIRE(fesetenv(&saved) == 0);
#if defined(__riscv_vector)
  __asm__ volatile ("csrw vcsr, %0" :: "r"(saved_vcsr) : "memory");
  printf("GROUPED_PV_PASS backend=RVV cases=%u invalid=%u csr=fcsr_vcsr rounding=RNE\n",
         cases, rejected);
#else
  printf("GROUPED_PV_PASS backend=scalar cases=%u invalid=%u csr=host_fenv rounding=RNE\n",
         cases, rejected);
#endif
  return 0;
}
#endif
