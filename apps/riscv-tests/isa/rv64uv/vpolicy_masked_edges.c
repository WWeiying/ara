// Exercise tail and mask policy on a predicated destination instruction.

#include "vector_macros.h"

#define ELEMENTS 16
#define ACTIVE_VL 13

static uint8_t lhs[ELEMENTS] __attribute__((aligned(128)));
static uint8_t rhs[ELEMENTS] __attribute__((aligned(128)));
static uint8_t initial[ELEMENTS] __attribute__((aligned(128)));
static uint8_t mask_bits[ELEMENTS] __attribute__((aligned(128))) = {0x55, 0x15};
static volatile uint8_t observed[ELEMENTS] __attribute__((aligned(128)));

static void check_result(unsigned tail_undisturbed, unsigned mask_undisturbed) {
  for (unsigned i = 0; i < ELEMENTS; ++i) {
    const unsigned active = i < ACTIVE_VL;
    const unsigned selected = active && ((mask_bits[i / 8] >> (i % 8)) & 1u);
    if (!selected && !((active && mask_undisturbed) ||
                       (!active && tail_undisturbed))) {
      continue;
    }
    const uint8_t expected = selected ? (uint8_t)(lhs[i] + rhs[i]) : initial[i];
    if (observed[i] != expected) {
      printf("policy result failed: i=%d got=%x expected=%x tu=%d mu=%d\n",
             i, observed[i], expected, tail_undisturbed, mask_undisturbed);
      ++num_failed;
      return;
    }
  }
}

#define RUN_POLICY(TAIL, MASK)                                            \
  do {                                                                    \
    asm volatile(                                                         \
        "vsetvli zero, %[all], e8, m1, tu, mu\n"                        \
        "vle8.v v0, (%[mask])\n"                                        \
        "vle8.v v1, (%[lhs])\n"                                         \
        "vle8.v v2, (%[rhs])\n"                                         \
        "vle8.v v3, (%[initial])\n"                                     \
        "vsetvli zero, %[active], e8, m1, " #TAIL ", " #MASK "\n"     \
        "vadd.vv v3, v1, v2, v0.t\n"                                    \
        "vsetvli zero, %[all], e8, m1, tu, mu\n"                        \
        "vse8.v v3, (%[observed])\n"                                    \
        "fence rw, rw\n"                                                \
        :                                                                 \
        : [all] "r"(ELEMENTS), [active] "r"(ACTIVE_VL),                 \
          [mask] "r"(mask_bits), [lhs] "r"(lhs), [rhs] "r"(rhs),          \
          [initial] "r"(initial), [observed] "r"(observed)              \
        : "memory");                                                     \
    check_result(#TAIL[1] == 'u', #MASK[1] == 'u');                      \
  } while (0)

int main(void) {
  INIT_CHECK();
  enable_vec();
  for (unsigned i = 0; i < ELEMENTS; ++i) {
    lhs[i] = 0x10 + i;
    rhs[i] = 0x20 + i;
    initial[i] = 0x80 + i;
  }

  RUN_POLICY(tu, mu);
  RUN_POLICY(tu, ma);
  RUN_POLICY(ta, mu);
  RUN_POLICY(ta, ma);
  EXIT_CHECK();
}
