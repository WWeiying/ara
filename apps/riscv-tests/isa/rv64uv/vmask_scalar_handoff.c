// Regression for exclusive ownership of lane 0's MaskB scalar-move response.

#include "vector_macros.h"

#define VLEN_BYTES 128
#define VLEN_WORDS (VLEN_BYTES / sizeof(uint64_t))
#define ACTIVE_BITS 79

static uint64_t source_a[VLEN_WORDS] __attribute__((aligned(128)));
static uint64_t source_b[VLEN_WORDS] __attribute__((aligned(128)));
static uint64_t initial_d[VLEN_WORDS] __attribute__((aligned(128)));
static uint64_t observed[VLEN_WORDS] __attribute__((aligned(128)));

static uint64_t low_bits(unsigned count) {
  if (count >= 64) return UINT64_MAX;
  return count == 0 ? 0 : (UINT64_C(1) << count) - 1;
}

int main(void) {
  INIT_CHECK();
  enable_vec();

  for (unsigned word = 0; word < VLEN_WORDS; ++word) {
    source_a[word] = UINT64_C(0x9669699696696996) ^
                     (UINT64_C(0x0101010101010101) * word);
    source_b[word] = UINT64_C(0x3cc3a55ac33c5aa5) ^
                     (UINT64_C(0x0303030303030303) * word);
    initial_d[word] = UINT64_C(0xa55a0ff05aa5f00f) ^
                      (UINT64_C(0x0707070707070707) * word);
  }

  unsigned long scalar_result;
  asm volatile(
      "vsetvli zero, zero, e8, m1, tu, mu\n"
      "vl1re8.v v31, (%[scalar_source])\n"
      "vmv.x.s %[scalar_result], v31\n"
      "vl1re8.v v1, (%[lhs])\n"
      "vl1re8.v v2, (%[rhs])\n"
      "vl1re8.v v3, (%[initial])\n"
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vmor.mm v3, v1, v2\n"
      "vs1r.v v3, (%[output])\n"
      "fence rw, rw\n"
      : [scalar_result] "=&r"(scalar_result)
      : [scalar_source] "r"(initial_d), [lhs] "r"(source_a),
        [rhs] "r"(source_b), [initial] "r"(initial_d),
        [output] "r"(observed), [vl] "r"((unsigned)ACTIVE_BITS)
      : "memory");

  if ((uint8_t)scalar_result != (uint8_t)initial_d[0]) {
    printf("mask scalar handoff failed: scalar got=%x expected=%x\n",
           (unsigned)(uint8_t)scalar_result, (unsigned)(uint8_t)initial_d[0]);
    ++num_failed;
  }

  for (unsigned word = 0; word < VLEN_WORDS; ++word) {
    unsigned base = word * 64;
    unsigned active = ACTIVE_BITS <= base ? 0
                        : ACTIVE_BITS >= base + 64 ? 64
                        : ACTIVE_BITS - base;
    uint64_t active_mask = low_bits(active);
    uint64_t expected = ((source_a[word] | source_b[word]) & active_mask) |
                        (initial_d[word] & ~active_mask);
    if (observed[word] != expected) {
      printf("mask scalar handoff failed: word=%d got=%lx expected=%lx\n",
             word, observed[word], expected);
      ++num_failed;
      break;
    }
  }

  EXIT_CHECK();
}
