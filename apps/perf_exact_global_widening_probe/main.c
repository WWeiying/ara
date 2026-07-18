// SPDX-License-Identifier: Apache-2.0
// Directed FP16->FP32 widening checks for the global exact reduction path.

#include <stdint.h>

#include "printf.h"
#include "runtime.h"

typedef struct {
  const char *name;
  uint16_t input[4];
  uint32_t seed;
  uint32_t expected;
  uint32_t expected_fflags;
  uint32_t mask;
  uint32_t masked;
} widening_case_t;

static const widening_case_t __attribute__((aligned(32))) cases[] = {
    {
        "basic",
        {0x3c00, 0x4000, 0x0000, 0x0000},
        0x00000000,
        0x40400000,
        0x00,
        0x0f,
        0,
    },
    {
        "cross-lane cancellation",
        {0x7bff, 0x3c00, 0xfbff, 0x0000},
        0x00000000,
        0x3f800000,
        0x00,
        0x0f,
        0,
    },
    {
        "active signaling NaN",
        {0x7c01, 0x0000, 0x0000, 0x0000},
        0x00000000,
        0x7fc00000,
        0x10,
        0x0f,
        0,
    },
    {
        "masked signaling NaN",
        {0x7c01, 0x3c00, 0x0000, 0x0000},
        0x00000000,
        0x3f800000,
        0x00,
        0x02,
        1,
    },
    {
        "all-masked fp32 seed copy",
        {0x7c00, 0xfc00, 0x7c01, 0x7e55},
        0x7f800001,
        0x7f800001,
        0x00,
        0x00,
        1,
    },
};

static void run_case(const widening_case_t *test, uint64_t *result,
                     uint64_t *fflags) {
  const uint64_t seed = test->seed;
  const uint64_t mask = test->mask;

  if (test->masked) {
    asm volatile(
        // The widening scalar is a binary32 value even though the source
        // vector type is binary16.
        "li t0, 1\n"
        "vsetvli t0, t0, e32, m1, ta, ma\n"
        "vmv.s.x v2, %[seed]\n"
        "li t0, 4\n"
        "vsetvli t0, t0, e16, m1, ta, ma\n"
        "vle16.v v1, (%[src])\n"
        "vmv.s.x v0, %[mask]\n"
        "csrwi frm, 0\n"
        "csrw fflags, zero\n"
        "vfwredusum.vs v4, v1, v2, v0.t\n"
        "li t0, 1\n"
        "vsetvli t0, t0, e32, m1, ta, ma\n"
        "vmv.x.s %[dst], v4\n"
        "csrr %[flags], fflags\n"
        : [dst] "=&r"(*result), [flags] "=&r"(*fflags)
        : [src] "r"(test->input), [seed] "r"(seed), [mask] "r"(mask)
        : "t0", "memory");
  } else {
    asm volatile(
        "li t0, 1\n"
        "vsetvli t0, t0, e32, m1, ta, ma\n"
        "vmv.s.x v2, %[seed]\n"
        "li t0, 4\n"
        "vsetvli t0, t0, e16, m1, ta, ma\n"
        "vle16.v v1, (%[src])\n"
        "csrwi frm, 0\n"
        "csrw fflags, zero\n"
        "vfwredusum.vs v4, v1, v2\n"
        "li t0, 1\n"
        "vsetvli t0, t0, e32, m1, ta, ma\n"
        "vmv.x.s %[dst], v4\n"
        "csrr %[flags], fflags\n"
        : [dst] "=&r"(*result), [flags] "=&r"(*fflags)
        : [src] "r"(test->input), [seed] "r"(seed)
        : "t0", "memory");
  }
}

int main(void) {
  uint64_t mismatch = 0;

  for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
    uint64_t result;
    uint64_t fflags;
    run_case(&cases[i], &result, &fflags);
    const int failed = (uint32_t)result != cases[i].expected ||
                       (uint32_t)fflags != cases[i].expected_fflags;
    mismatch |= failed;
    printf("global exact widening %s: result=%lx/%x fflags=%lx/%x (%s)\n",
           cases[i].name, result, cases[i].expected, fflags,
           cases[i].expected_fflags, failed ? "FAILED" : "PASSED");
  }

  return mismatch != 0;
}
