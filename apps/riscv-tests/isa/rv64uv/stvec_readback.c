// SPDX-License-Identifier: Apache-2.0
// Non-CLIC STVEC WARL/readback matrix; vector trap delivery is a separate gate.
#include "vector_macros.h"

#if !defined(__clang__) || defined(vec) || defined(ARA_FPGA) || defined(ARA_LINUX) || defined(__SPIKE__)
#error "Use the non-ZCC scalar-C bare-metal SoC build"
#endif

static volatile unsigned completed;
static unsigned failures;
static uint64_t first_actual, first_expected, first_written;

static void check(uint64_t actual, uint64_t expected, uint64_t written) {
  ++test_case;
  if (actual != expected) {
    if (!failures) {
      first_actual = actual; first_expected = expected; first_written = written;
    }
    ++failures;
  }
}

void rvtest_init(void) {
  uint64_t old, status, old_mie, previous, actual;
  asm volatile("csrrci %0, mstatus, 8\ncsrrw %1, mie, zero\ncsrr %2, stvec\n"
               : "=&r"(status), "=&r"(old_mie), "=r"(old) : : "memory");
  const uint64_t entry_stvec = old;
  previous = old;
  for (unsigned high = 0; high < 2; ++high)
    for (unsigned mode = 0; mode < 2; ++mode)
      for (unsigned off = 0; off < 256; off += 4) {
        uint64_t written = (high ? UINT64_C(0xffffffff80001000) : UINT64_C(0x80001000)) + off + mode;
        uint64_t expected = mode ? (written & ~UINT64_C(255)) | 1 : written;
        asm volatile("csrrw %0, stvec, %2\ncsrr %1, stvec"
                     : "=&r"(actual), "=r"(old) : "r"(written) : "memory");
        check(actual, previous, written); check(old, expected, written);
        previous = expected;
      }
  // Reserved MODE bit 1 remains WARL zero, matching the existing interface.
  for (unsigned mode = 2; mode < 4; ++mode) {
    uint64_t written = UINT64_C(0x8000107c) | mode;
    uint64_t expected = (mode & 1) ? UINT64_C(0x80001001) : UINT64_C(0x8000107c);
    asm volatile("csrw stvec, %1\ncsrr %0, stvec" : "=r"(actual) : "r"(written) : "memory");
    check(actual, expected, written);
  }
  asm volatile("csrw stvec, %0\ncsrw mie, %1\ncsrw mstatus, %2"
               : : "r"(entry_stvec), "r"(old_mie), "r"(status) : "memory");
  completed = 1;
}

int main(void) {
  printf("stvec_readback: checks=%d failures=%u first_write=%lx got=%lx expected=%lx\n",
         test_case, failures, first_written, first_actual, first_expected);
  if (!completed || failures || test_case != 514) {
    printf("FAIL: stvec_readback\n"); return 1;
  }
  printf("PASSED: stvec_readback\n"); return 0;
}
