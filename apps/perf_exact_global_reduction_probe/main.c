// SPDX-License-Identifier: Apache-2.0
// Directed cross-lane numerical and fflags checks for global exact FP32
// reduction.

#include <stdint.h>

#include "printf.h"
#include "runtime.h"

typedef struct {
  const char *name;
  uint32_t input[4];
  uint32_t seed;
  uint32_t expected;
  uint32_t expected_fflags;
} reduction_case_t;

static const reduction_case_t __attribute__((aligned(32))) cases[] = {
    {
        "cross-lane cancellation",
        {0x60ad78ec, 0x3f800000, 0xe0ad78ec, 0x00000000},
        0x00000000,
        0x3f800000,
        0x00,
    },
    {
        "opposite infinities",
        {0x7f800000, 0xff800000, 0x00000000, 0x00000000},
        0x00000000,
        0x7fc00000,
        0x10,
    },
    {
        "signaling NaN",
        {0x7f800001, 0x00000000, 0x00000000, 0x00000000},
        0x00000000,
        0x7fc00000,
        0x10,
    },
    {
        "quiet NaN",
        {0x7fc12345, 0x00000000, 0x00000000, 0x00000000},
        0x00000000,
        0x7fc00000,
        0x00,
    },
    {
        "positive overflow",
        {0x7f7fffff, 0x7f7fffff, 0x7f7fffff, 0x7f7fffff},
        0x00000000,
        0x7f800000,
        0x05,
    },
    {
        "half-ulp tie-to-even",
        {0x3f800000, 0x33800000, 0x00000000, 0x00000000},
        0x00000000,
        0x3f800000,
        0x01,
    },
    {
        "exact subnormal",
        {0x00000001, 0x00000001, 0x00000000, 0x00000000},
        0x00000000,
        0x00000002,
        0x00,
    },
};

static void run_reduction(const reduction_case_t *test, uint64_t *result,
                          uint64_t *fflags) {
  const uint64_t seed = test->seed;

  // Consecutive elements are striped over the four lanes.  Rounding the
  // lane-0/lane-1 partial before it meets lane 2 loses the unit term; merging
  // the exported exact states first must retain it.
  asm volatile(
      "li t0, 4\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      "vle32.v v1, (%[src])\n"
      "vmv.s.x v2, %[seed]\n"
      "csrwi frm, 0\n"
      "csrw fflags, zero\n"
      "vfredusum.vs v3, v1, v2\n"
      "vmv.x.s %[dst], v3\n"
      "csrr %[flags], fflags\n"
      : [dst] "=&r"(*result), [flags] "=&r"(*fflags)
      : [src] "r"(test->input), [seed] "r"(seed)
      : "t0", "memory");
}

int main(void) {
  uint64_t mismatch = 0;

  for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
    uint64_t result;
    uint64_t fflags;
    run_reduction(&cases[i], &result, &fflags);
    const int failed = (uint32_t)result != cases[i].expected ||
                       (uint32_t)fflags != cases[i].expected_fflags;
    mismatch |= failed;
    printf("global exact %s: result=%lx/%x fflags=%lx/%x (%s)\n",
           cases[i].name, result, cases[i].expected, fflags,
           cases[i].expected_fflags, failed ? "FAILED" : "PASSED");
  }

  return mismatch != 0;
}
