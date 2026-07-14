#include <stdint.h>

#include "printf.h"
#include "runtime.h"

#define FOUR_REDUCTIONS(OP)                                                   \
  OP " v4, v1, v2\n" OP " v5, v1, v2\n" OP " v6, v1, v2\n" OP " v7, v1, v2\n"

#define CHECK_FOUR(EXPECTED)                                                  \
  "li t4, " EXPECTED "\n"                                                  \
  "vmv.x.s t3, v4\n xor t3, t3, t4\n or t2, t2, t3\n"                 \
  "vmv.x.s t3, v5\n xor t3, t3, t4\n or t2, t2, t3\n"                 \
  "vmv.x.s t3, v6\n xor t3, t3, t4\n or t2, t2, t3\n"                 \
  "vmv.x.s t3, v7\n xor t3, t3, t4\n or t2, t2, t3\n"

#define FOUR_WIDE_REDUCTIONS(OP)                                              \
  OP " v4, v8, v2\n" OP " v6, v8, v2\n" OP " v10, v8, v2\n"                 \
     OP " v14, v8, v2\n"

#define CHECK_FOUR_WIDE(EXPECTED)                                             \
  "li t4, " EXPECTED "\n"                                                  \
  "vmv.x.s t3, v4\n xor t3, t3, t4\n or t2, t2, t3\n"                 \
  "vmv.x.s t3, v6\n xor t3, t3, t4\n or t2, t2, t3\n"                 \
  "vmv.x.s t3, v10\n xor t3, t3, t4\n or t2, t2, t3\n"                \
  "vmv.x.s t3, v14\n xor t3, t3, t4\n or t2, t2, t3\n"

int main(void) {
  uint64_t result;

  asm volatile(
      "li t0, 32\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      "vmv.v.i v1, 1\n"
      "vmv.v.i v2, 0\n"
      "vmv.x.s t1, v2\n"
      "li t2, 0\n"
      FOUR_REDUCTIONS("vredsum.vs")
      CHECK_FOUR("32")
      "vmv.v.i v2, -1\n"
      "vmv.x.s t1, v2\n"
      FOUR_REDUCTIONS("vredand.vs")
      CHECK_FOUR("1")
      "vmv.v.i v2, 0\n"
      "vmv.x.s t1, v2\n"
      FOUR_REDUCTIONS("vredor.vs")
      CHECK_FOUR("1")
      FOUR_REDUCTIONS("vredxor.vs")
      CHECK_FOUR("0")
      "vmv.v.i v2, 5\n"
      "vmv.x.s t1, v2\n"
      FOUR_REDUCTIONS("vredminu.vs")
      CHECK_FOUR("1")
      FOUR_REDUCTIONS("vredmin.vs")
      CHECK_FOUR("1")
      "vmv.v.i v2, 0\n"
      "vmv.x.s t1, v2\n"
      FOUR_REDUCTIONS("vredmaxu.vs")
      CHECK_FOUR("1")
      FOUR_REDUCTIONS("vredmax.vs")
      CHECK_FOUR("1")
      // Widening reductions use EMUL=2, hence every architectural vector
      // register operand and destination below starts at an even index.
      "vmv.v.i v8, 1\n"
      "vmv.x.s t1, v8\n"
      FOUR_WIDE_REDUCTIONS("vwredsumu.vs")
      CHECK_FOUR_WIDE("32")
      FOUR_WIDE_REDUCTIONS("vwredsum.vs")
      CHECK_FOUR_WIDE("32")
      "mv %[result], t2\n"
      : [result] "=&r"(result)
      :
      : "t0", "t1", "t2", "t3", "t4", "memory");

  const int failed = result != 0;
  printf("integer reduction stream probe: result=%lx (%s)\n", result,
         failed ? "FAILED" : "PASSED");
  return failed;
}
