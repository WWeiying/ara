#include <stdint.h>

#include "printf.h"
#include "runtime.h"

#define CHECK_BIT(REG, EXPECTED, BIT)                                         \
  "li t4, " EXPECTED "\n"                                                   \
  "vmv.x.s t3, " REG "\n"                                                   \
  "xor t3, t3, t4\n"                                                        \
  "snez t3, t3\n"                                                           \
  "slli t3, t3, " BIT "\n"                                                  \
  "or t2, t2, t3\n"

int main(void) {
  uint64_t result;

  asm volatile(
      "li t0, 32\n"
      "vsetvli t0, t0, e32, m1, ta, ma\n"
      // Select elements 0..15.  Every streamed instruction consumes its own
      // mask token; reusing v0 makes any missing mask-ready handshake visible
      // as either a deadlock or an incorrect result.
      "vid.v v3\n"
      "vmsltu.vi v0, v3, 16\n"
      "vmv.v.i v1, 1\n"
      "vmv.v.i v2, 7\n"
      "vmv.x.s t1, v2\n"
      "fence\n"
      "rdcycle zero\n"
      "vredsum.vs v4,  v1, v2, v0.t\n"
      "vredsum.vs v5,  v1, v2, v0.t\n"
      "vredsum.vs v6,  v1, v2, v0.t\n"
      "vredsum.vs v7,  v1, v2, v0.t\n"
      "vredsum.vs v8,  v1, v2, v0.t\n"
      "vredsum.vs v9,  v1, v2, v0.t\n"
      "vredsum.vs v10, v1, v2, v0.t\n"
      "vredsum.vs v11, v1, v2, v0.t\n"
      // +1.0 * 16 active elements plus a +5.0 scalar seed = +21.0.
      "li t0, 0x3f800000\n"
      "vmv.v.x v1, t0\n"
      "li t0, 0x40a00000\n"
      "vmv.v.x v2, t0\n"
      "vfredusum.vs v12, v1, v2, v0.t\n"
      "vfredusum.vs v13, v1, v2, v0.t\n"
      "vfredusum.vs v14, v1, v2, v0.t\n"
      "vfredusum.vs v15, v1, v2, v0.t\n"
      "vfredusum.vs v16, v1, v2, v0.t\n"
      "vfredusum.vs v17, v1, v2, v0.t\n"
      "vfredusum.vs v18, v1, v2, v0.t\n"
      "vfredusum.vs v19, v1, v2, v0.t\n"
      "vmv.x.s t1, v19\n"
      "fence\n"
      "rdcycle zero\n"
      "li t2, 0\n"
      CHECK_BIT("v4", "23", "0") CHECK_BIT("v5", "23", "1")
      CHECK_BIT("v6", "23", "2") CHECK_BIT("v7", "23", "3")
      CHECK_BIT("v8", "23", "4") CHECK_BIT("v9", "23", "5")
      CHECK_BIT("v10", "23", "6") CHECK_BIT("v11", "23", "7")
      CHECK_BIT("v12", "0x41a80000", "8")
      CHECK_BIT("v13", "0x41a80000", "9")
      CHECK_BIT("v14", "0x41a80000", "10")
      CHECK_BIT("v15", "0x41a80000", "11")
      CHECK_BIT("v16", "0x41a80000", "12")
      CHECK_BIT("v17", "0x41a80000", "13")
      CHECK_BIT("v18", "0x41a80000", "14")
      CHECK_BIT("v19", "0x41a80000", "15")
      "mv %[result], t2\n"
      : [result] "=&r"(result)
      :
      : "t0", "t1", "t2", "t3", "t4", "memory");

  const int failed = result != 0;
  printf("masked reduction stream probe: result=%lx (%s)\n", result,
         failed ? "FAILED" : "PASSED");
  return failed;
}
