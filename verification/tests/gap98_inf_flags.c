// SPDX-License-Identifier: SHL-0.51
// Spike-only isolation: mixed finite/Inf batches cannot prove Inf flags alone.
#include "vector_macros.h"

volatile unsigned g75_result[2];
static uint16_t lhs[128] __attribute__((aligned(128)));
static uint16_t rhs[128] __attribute__((aligned(128)));
static uint16_t output[128] __attribute__((aligned(128)));

int main(void) {
  INIT_CHECK(); enable_vec(); enable_fp();
  unsigned checks = 0;
  for (unsigned negative = 0; negative < 2; ++negative) {
    unsigned sign = negative << 15;
    for (unsigned i = 0; i < 128; ++i) {
      lhs[i] = sign | 1;
      rhs[i] = 0x7c00;
      output[i] = 0xa55a;
    }
    unsigned long flags, restart, vl;
    asm volatile(
      "vsetvli %[vl], %[count], e16, m2, tu, mu\n"
      "vle16.v v8, (%[lhs])\nvle16.v v4, (%[rhs])\n"
      "csrw frm, zero\ncsrw fflags, zero\n"
      "vfdiv.vv v16, v8, v4\n"
      "csrr %[flags], fflags\ncsrr %[restart], vstart\n"
      "vse16.v v16, (%[output])\n"
      : [flags] "=&r"(flags), [restart] "=&r"(restart), [vl] "=&r"(vl)
      : [count] "r"(128ul), [lhs] "r"(lhs), [rhs] "r"(rhs), [output] "r"(output)
      : "memory", "v4", "v5", "v8", "v9", "v16", "v17");
    for (unsigned i = 0; i < 128; ++i) {
      checks += 3;
      if (output[i] != sign) ++num_failed;
      if (lhs[i] != (sign | 1)) ++num_failed;
      if (rhs[i] != 0x7c00) ++num_failed;
    }
    checks += 3;
    if (flags != 0) ++num_failed;
    if (restart != 0) ++num_failed;
    if (vl != 128) ++num_failed;
  }
  g75_result[0] = checks;
  g75_result[1] = num_failed;
  return num_failed || checks != 774;
}
