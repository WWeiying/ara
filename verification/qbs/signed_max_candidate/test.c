#include "signed_max.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

static uint32_t bits(float x) { uint32_t v; memcpy(&v, &x, 4); return v; }
static float from_bits(uint32_t x) { float v; memcpy(&v, &x, 4); return v; }
static unsigned read_fcsr(void) { unsigned v; asm volatile("frcsr %0" : "=r"(v)); return v; }
static unsigned read_vcsr(void) { unsigned v; asm volatile("csrr %0,vcsr" : "=r"(v)); return v; }
static void set_csrs(unsigned f, unsigned v) {
  asm volatile("fscsr %0; csrw vcsr,%1" :: "r"(f), "r"(v) : "memory");
}
__attribute__((noinline)) static float reference(const float *x, size_t n, float *absolute) {
  float a = 0.0f, maximum = 0.0f;
  for (size_t i = 0; i < n; ++i) {
    if (a < fabsf(x[i])) { a = fabsf(x[i]); maximum = x[i]; }
  }
  *absolute = a;
  return maximum;
}
static size_t cases, checks;
static void check(const float *x, size_t n) {
  const unsigned flags[] = {0, 1, 16, 31};
  ++cases;
  for (unsigned frm = 0; frm < 5; ++frm) {
    for (unsigned f = 0; f < 4; ++f) {
      for (unsigned vc = 0; vc < 8; ++vc) {
        unsigned fc = (frm << 5) | flags[f];
        set_csrs(fc, vc);
        float a, b;
        float old = reference(x, n, &a);
        unsigned old_fc = read_fcsr(), old_vc = read_vcsr();
        set_csrs(fc, vc);
        float candidate = qbs_signed_max_candidate(x, n, &b);
        unsigned new_fc = read_fcsr(), new_vc = read_vcsr();
        ++checks;
        if (bits(old) != bits(candidate) || bits(a) != bits(b) || old_fc != new_fc ||
            old_vc != new_vc || new_fc != fc || new_vc != vc) {
          fprintf(stderr, "SIGNED_MAX_FAIL case=%zu n=%zu frm=%u flags=%u vcsr=%u\n",
                  cases, n, frm, flags[f], vc);
          exit(1);
        }
      }
    }
  }
}
int main(void) {
  unsigned saved_fc = read_fcsr(), saved_vc = read_vcsr();
  float x[257];
  const size_t lengths[] = {0,1,15,16,17,31,32,33,127,128,129,255,256,257};
  for (size_t t = 0; t < sizeof(lengths)/sizeof(lengths[0]); ++t) {
    size_t n = lengths[t];
    for (size_t j = 0; j < n; ++j) x[j] = from_bits((j & 1) ? 0x80000000u : 0);
    check(x, n);
    for (size_t pos = 0; pos < n; ++pos) {
      for (size_t j = 0; j < n; ++j) x[j] = (j & 1) ? -1.0f : 1.0f;
      x[pos] = (pos & 1) ? -2.0f : 2.0f;
      if (pos + 1 < n) x[pos + 1] = -x[pos];
      check(x, n);
    }
  }
  const uint32_t values[] = {1, 0x007fffff, 0x00800000, 0x7f7fffff};
  for (size_t t = 0; t < sizeof(values)/sizeof(values[0]); ++t) {
    for (size_t j = 0; j < 257; ++j) x[j] = from_bits(values[t] | ((j & 1) ? 0x80000000u : 0));
    check(x, 257);
  }
  set_csrs(saved_fc, saved_vc);
  printf("SIGNED_MAX_PASS cases=%zu checks=%zu exact=1 csr=1 performance=not_measured\n", cases, checks);
  return 0;
}
