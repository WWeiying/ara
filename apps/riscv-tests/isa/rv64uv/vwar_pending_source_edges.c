// WAR regression for a source command waiting at the lane/requester boundary.

#include "vector_macros.h"

#define ELEMENTS 333

static uint16_t mul_source[ELEMENTS] __attribute__((aligned(128)));
static uint16_t sub_source[ELEMENTS] __attribute__((aligned(128)));
static uint16_t waw_source[ELEMENTS] __attribute__((aligned(128)));
static uint16_t sub_result[ELEMENTS] __attribute__((aligned(128)));
static uint16_t mul_result[ELEMENTS] __attribute__((aligned(128)));

static void initialize_data(void) {
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    mul_source[index] = (uint16_t)(3u + 17u * index);
    sub_source[index] = (uint16_t)(0x014cu + 29u * index);
    waw_source[index] = (uint16_t)(0x31u + 11u * index);
    sub_result[index] = 0;
    mul_result[index] = 0;
  }
}

int main(void) {
  const unsigned long scalar = 0xd9e0a266UL;

  INIT_CHECK();
  enable_vec();
  initialize_data();

  asm volatile(
      "vsetvli zero, %[vl], e16, m8, tu, mu\n"
      "vle16.v v0, (%[mul_source])\n"
      "vle16.v v8, (%[sub_source])\n"
      "vle16.v v16, (%[waw_source])\n"
      // Keep the older vsub behind a WAW while its v8 source command waits
      // for the shared ALU operand requester. The younger vmul must not write
      // v8 until that pending source has been captured.
      "vsll.vi v24, v16, 13\n"
      "vsub.vx v24, v8, %[scalar]\n"
      "vmul.vv v8, v0, v0\n"
      "vse16.v v24, (%[sub_result])\n"
      "vse16.v v8, (%[mul_result])\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(ELEMENTS), [scalar] "r"(scalar),
        [mul_source] "r"(mul_source), [sub_source] "r"(sub_source),
        [waw_source] "r"(waw_source), [sub_result] "r"(sub_result),
        [mul_result] "r"(mul_result)
      : "memory");

  for (unsigned index = 0; index < ELEMENTS; ++index) {
    uint16_t expected_sub =
        (uint16_t)((uint32_t)sub_source[index] - (uint16_t)scalar);
    uint16_t expected_mul =
        (uint16_t)((uint32_t)mul_source[index] * mul_source[index]);
    if (sub_result[index] != expected_sub) {
      printf("pending-source WAR sub failed at %d: got=%x expected=%x\n",
             index, sub_result[index], expected_sub);
      ++num_failed;
      break;
    }
    if (mul_result[index] != expected_mul) {
      printf("pending-source WAR mul failed at %d: got=%x expected=%x\n",
             index, mul_result[index], expected_mul);
      ++num_failed;
      break;
    }
  }

  EXIT_CHECK();
}
