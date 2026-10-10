// SPDX-License-Identifier: Apache-2.0
// Empty lanes must use the same packet protocol as populated lanes. Exercise
// mask credit, early release, and late seeds with exact integer-valued sums.
#include <stdint.h>
#include "printf.h"
#include "runtime.h"
#define REDUCE(OP) do { \
  if (mask_kind == 0) \
    asm volatile(OP " v4, v1, v2\n" OP " v4, v1, v4\n" OP " v4, v1, v4\n" ::: "memory"); \
  else \
    asm volatile(OP " v4, v1, v2, v0.t\n" OP " v4, v1, v4, v0.t\n" OP " v4, v1, v4, v0.t\n" ::: "memory"); \
} while (0)
static int check(unsigned vl, unsigned format, unsigned mask_kind) {
  uint64_t result, flags;
  // Seed is FP32 for native FP32 and widening, otherwise FP16.
  unsigned seed = format == 1 ? 0x3c00 : 0x3f800000;
  asm volatile("li t0, 1\n vsetvli t0, t0, e32, m1, tu, mu\n vmv.v.x v2, %[seed]\n"
               :: [seed] "r"((uint64_t)seed) : "t0", "memory");
  if (format == 0)
    asm volatile("vsetvli zero, %[vl], e32, m1, tu, mu\n li t0, 0x3f800000\n vmv.v.x v1, t0\n"
                 :: [vl] "r"((uint64_t)vl) : "t0", "memory");
  else
    asm volatile("vsetvli zero, %[vl], e16, m1, tu, mu\n li t0, 0x3c00\n vmv.v.x v1, t0\n"
                 :: [vl] "r"((uint64_t)vl) : "t0", "memory");
  asm volatile("vmv.v.i v0, 0" ::: "memory");
  if (mask_kind == 2) asm volatile("vmclr.m v0" ::: "memory");
  else asm volatile("vmset.m v0" ::: "memory");
  asm volatile("csrwi fflags, 0\n rdcycle zero" ::: "memory");
  if (format == 2) REDUCE("vfwredusum.vs");
  else REDUCE("vfredusum.vs");
  if (format == 2)
    asm volatile("li t0, 1\n vsetvli t0, t0, e32, m1, tu, mu" ::: "t0", "memory");
  asm volatile("vmv.x.s %[result], v4\n csrr %[flags], fflags\n rdcycle zero"
               : [result] "=&r"(result), [flags] "=&r"(flags) :: "memory");
  unsigned expected_int = 1 + (mask_kind == 2 ? 0 : 3 * vl);
  union { float f; uint32_t u; } expected = {.f = (float)expected_int};
  // All integers here are exactly representable in both binary16 and binary32.
  uint32_t bits = format == 1 ? ((expected.u >> 13) & 0x3ff) |
                  (((expected.u >> 23) - 112) << 10) : expected.u;
  if (result != bits || flags != 0) {
    printf("length audit FAIL vl=%u format=%u mask=%u result=%lx expected=%x flags=%lx\n",
           vl, format, mask_kind, result, bits, flags);
    return 1;
  }
  return 0;
}
int main(void) {
  static const unsigned lengths[] = {1,2,3,4,5,7,8,15,16,31,32};
  for (unsigned format = 0; format < 3; ++format)
    for (unsigned mask = 0; mask < 3; ++mask)
      for (unsigned i = 0; i < sizeof(lengths)/sizeof(lengths[0]); ++i)
        if (check(lengths[i], format, mask)) return 1;
  printf("length audit: 99 cases of three dependent reductions PASS\n");
  return 0;
}
