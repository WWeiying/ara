// Reduction register-group legality and result tracking regressions.

#include "vector_macros.h"

#define ELEMENTS 13
#define LONG_ELEMENTS 300

static uint32_t integer_source[ELEMENTS] __attribute__((aligned(128))) = {
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13};
static uint32_t integer_seed __attribute__((aligned(128))) = 17;
static uint32_t integer_result __attribute__((aligned(128)));

static int16_t widening_source[ELEMENTS] __attribute__((aligned(128))) = {
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13};
static int32_t widening_seed __attribute__((aligned(128))) = -7;
static int32_t widening_result __attribute__((aligned(128)));

static uint64_t fp_source[ELEMENTS] __attribute__((aligned(128))) = {
    UINT64_C(0x4020000000000000), UINT64_C(0x401c000000000000),
    UINT64_C(0x4018000000000000), UINT64_C(0x4014000000000000),
    UINT64_C(0x4010000000000000), UINT64_C(0x4008000000000000),
    UINT64_C(0x4000000000000000), UINT64_C(0x3ff0000000000000),
    UINT64_C(0xc000000000000000), UINT64_C(0x4008000000000000),
    UINT64_C(0x4010000000000000), UINT64_C(0x4014000000000000),
    UINT64_C(0x4018000000000000)};
static uint64_t fp_seed __attribute__((aligned(128))) =
    UINT64_C(0x4008000000000000);
static uint64_t fp_result __attribute__((aligned(128)));

static uint32_t widening_fp_source[ELEMENTS] __attribute__((aligned(128))) = {
    0x3f800000, 0x40000000, 0x40400000, 0x40800000, 0x40a00000,
    0x40c00000, 0x40e00000, 0x41000000, 0x41100000, 0x41200000,
    0x41300000, 0x41400000, 0x41500000};
static uint64_t widening_fp_seed __attribute__((aligned(128))) =
    UINT64_C(0x3ff0000000000000);
static uint64_t widening_fp_result __attribute__((aligned(128)));
static uint8_t long_source[LONG_ELEMENTS] __attribute__((aligned(128)));
static uint8_t long_first_mask[(LONG_ELEMENTS + 7) / 8]
    __attribute__((aligned(128)));
static uint8_t long_reduction_mask[(LONG_ELEMENTS + 7) / 8]
    __attribute__((aligned(128)));
static uint8_t long_seed __attribute__((aligned(128))) = 7;
static uint8_t long_result __attribute__((aligned(128)));

static void wait_for_vector(void) {
  unsigned long vl;
  asm volatile("csrr %0, vl\n fence rw, rw" : "=r"(vl) :: "memory");
}

static void test_integer_reduction(void) {
  asm volatile(
      "vsetivli zero, 1, e32, m1, tu, mu\n"
      "vle32.v v23, (%[seed])\n"
      "vsetvli zero, %[vl], e32, m4, tu, mu\n"
      "vle32.v v24, (%[source])\n"
      // vd and vs1 are deliberately not m4-aligned. They are single-register
      // reduction operands; only the v24-v27 source follows LMUL=4.
      "vredsum.vs v17, v24, v23\n"
      "vsetivli zero, 1, e32, m1, tu, mu\n"
      "vse32.v v17, (%[result])\n"
      :
      : [vl] "r"(ELEMENTS), [source] "r"(integer_source),
        [seed] "r"(&integer_seed), [result] "r"(&integer_result)
      : "memory");
  wait_for_vector();

  uint32_t expected = integer_seed;
  for (unsigned index = 0; index < ELEMENTS; ++index)
    expected += integer_source[index];
  if (integer_result != expected) {
    printf("LMUL integer reduction failed: got=%x expected=%x\n",
           integer_result, expected);
    ++num_failed;
  }
}

static void test_widening_reduction(void) {
  asm volatile(
      "vsetivli zero, 1, e32, m1, tu, mu\n"
      "vle32.v v23, (%[seed])\n"
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vle16.v v24, (%[source])\n"
      "vwredsum.vs v17, v24, v23\n"
      "vsetivli zero, 1, e32, m1, tu, mu\n"
      "vse32.v v17, (%[result])\n"
      :
      : [vl] "r"(ELEMENTS), [source] "r"(widening_source),
        [seed] "r"(&widening_seed), [result] "r"(&widening_result)
      : "memory");
  wait_for_vector();

  int32_t expected = widening_seed;
  for (unsigned index = 0; index < ELEMENTS; ++index)
    expected += widening_source[index];
  if (widening_result != expected) {
    printf("LMUL widening reduction failed: got=%x expected=%x\n",
           (uint32_t)widening_result, (uint32_t)expected);
    ++num_failed;
  }
}

static void test_fp_reduction(void) {
  asm volatile(
      "vsetivli zero, 1, e64, m1, tu, mu\n"
      "vle64.v v23, (%[seed])\n"
      "vsetvli zero, %[vl], e64, m4, tu, mu\n"
      "vle64.v v28, (%[source])\n"
      // This is the exact LMUL/register-shape class exposed by random seed 1.
      "vfredmin.vs v17, v28, v23\n"
      "vsetivli zero, 1, e64, m1, tu, mu\n"
      "vse64.v v17, (%[result])\n"
      :
      : [vl] "r"(ELEMENTS), [source] "r"(fp_source),
        [seed] "r"(&fp_seed), [result] "r"(&fp_result)
      : "memory");
  wait_for_vector();

  const uint64_t expected = UINT64_C(0xc000000000000000);
  if (fp_result != expected) {
    printf("LMUL FP reduction failed: got=%lx expected=%lx\n", fp_result,
           expected);
    ++num_failed;
  }
}

static void test_widening_fp_reduction(void) {
  asm volatile(
      "vsetivli zero, 1, e64, m1, tu, mu\n"
      "vle64.v v23, (%[seed])\n"
      "vsetvli zero, %[vl], e32, m4, tu, mu\n"
      "vle32.v v24, (%[source])\n"
      "vfwredusum.vs v19, v24, v23\n"
      "vsetivli zero, 1, e64, m1, tu, mu\n"
      "vse64.v v19, (%[result])\n"
      :
      : [vl] "r"(ELEMENTS), [source] "r"(widening_fp_source),
        [seed] "r"(&widening_fp_seed), [result] "r"(&widening_fp_result)
      : "memory");
  wait_for_vector();

  // 1.0 seed + sum(1.0 ... 13.0) = 92.0, exactly representable in FP64.
  const uint64_t expected = UINT64_C(0x4057000000000000);
  if (widening_fp_result != expected) {
    printf("LMUL widening FP reduction failed: got=%lx expected=%lx\n",
           widening_fp_result, expected);
    ++num_failed;
  }
}

static void test_vfirst_operand_drain(void) {
  for (unsigned index = 0; index < LONG_ELEMENTS; ++index)
    long_source[index] = 1;
  for (unsigned index = 0; index < sizeof(long_first_mask); ++index) {
    long_first_mask[index] = 0xff;
    long_reduction_mask[index] = 0xff;
  }

  long first = -1;
  asm volatile(
      "vsetvli zero, %[vl], e8, m4, tu, mu\n"
      "vle8.v v8, (%[source])\n"
      "vlm.v v1, (%[first_mask])\n"
      "vlm.v v0, (%[reduction_mask])\n"
      "vsetivli zero, 1, e8, m1, tu, mu\n"
      "vle8.v v6, (%[seed])\n"
      "vsetvli zero, %[vl], e8, m4, tu, mu\n"
      // The first match is in the first aggregate word, while VL extends into
      // the next one. VFIRST must still drain all requested operand words.
      "vfirst.m %[first], v1\n"
      "vredsum.vs v4, v8, v6, v0.t\n"
      "vsetivli zero, 1, e8, m1, tu, mu\n"
      "vse8.v v4, (%[result])\n"
      : [first] "=r"(first)
      : [vl] "r"(LONG_ELEMENTS), [source] "r"(long_source),
        [first_mask] "r"(long_first_mask),
        [reduction_mask] "r"(long_reduction_mask), [seed] "r"(&long_seed),
        [result] "r"(&long_result)
      : "memory");
  wait_for_vector();

  const uint8_t expected = (uint8_t)(long_seed + LONG_ELEMENTS);
  if (first != 0 || long_result != expected) {
    printf("vfirst operand drain failed: first=%ld result=%x expected=0:%x\n",
           first, long_result, expected);
    ++num_failed;
  }
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  enable_fp();
  test_integer_reduction();
  test_widening_reduction();
  test_fp_reduction();
  test_widening_fp_reduction();
  test_vfirst_operand_drain();
  EXIT_CHECK();
}
