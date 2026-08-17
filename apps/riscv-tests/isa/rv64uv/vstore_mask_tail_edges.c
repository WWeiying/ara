// Regression for masked stores at the end of a lane-interleaved mask word.

#include "vector_macros.h"

#define ELEMENTS 16

static uint8_t source[ELEMENTS] __attribute__((aligned(128))) = {
    0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17,
    0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0xa4};
static uint8_t mask_seed[ELEMENTS] __attribute__((aligned(128))) = {
    0x29, 0x26, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00};
static volatile uint8_t target[ELEMENTS] __attribute__((aligned(128))) = {
    0x5a, 0x5a, 0x5a, 0x5a, 0x5a, 0x5a, 0x5a, 0x5a,
    0x5a, 0x5a, 0x5a, 0x5a, 0x5a, 0x5a, 0x5a, 0x5a};

int main(void) {
  INIT_CHECK();
  enable_vec();

  asm volatile(
      "vsetvli zero, %[vl], e8, mf8, tu, mu\n"
      "vle8.v v0, (%[mask_seed])\n"
      "vid.v v28\n"
      "vadd.vv v0, v0, v28\n"
      "vsetvli zero, %[vl], e32, mf2, tu, mu\n"
      "vle8.v v10, (%[source])\n"
      "vse8.v v10, (%[target]), v0.t\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(ELEMENTS), [source] "r"(source),
        [mask_seed] "r"(mask_seed), [target] "r"(target)
      : "memory");

  for (unsigned i = 0; i < ELEMENTS; ++i) {
    uint8_t expected = ((0x2729u >> i) & 1u) ? source[i] : 0x5a;
    if (target[i] != expected) {
      printf("masked store tail failed at %d: got=%x expected=%x\n", i,
             target[i], expected);
      ++num_failed;
      break;
    }
  }

  EXIT_CHECK();
}
