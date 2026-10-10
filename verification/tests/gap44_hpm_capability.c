// SPDX-License-Identifier: SHL-0.51
// Spike capability measurement only, not a DUT preservation test.
#include <stdint.h>
#include <stdio.h>
#define READ(c, v) asm volatile("csrr %0, " #c : "=r"(v) : : "memory")
#define WRITE(c, v) asm volatile("csrw " #c ", %0" : : "r"((uint64_t)(v)) : "memory")

int main(void) {
  const uint64_t patterns[] = {UINT64_C(0x13579bdf2468ace0), UINT64_C(0xfedcba9876543210)};
  uint64_t count, event, got, shadow, stable;
  READ(0x323, event); READ(0xb03, count);
  WRITE(0x323, 0);
  for (unsigned i = 0; i < 2; ++i) {
    WRITE(0xb03, patterns[i]); READ(0xb03, got); READ(0xc03, shadow);
    asm volatile(".rept 16\nnop\n.endr" : : : "memory");
    READ(0xb03, stable);
    printf("HPM_CAP pattern=%lx read=%lx shadow=%lx stable=%lx\n",
           patterns[i], got, shadow, stable);
  }
  WRITE(0xb03, count); WRITE(0x323, event);
  return 0;
}
