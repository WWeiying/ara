// Mask-producing comparisons must not modify registers adjacent to vd.

#include "vector_macros.h"

#define VLEN_BYTES 128
#define VL 79

static uint16_t source[VL] __attribute__((aligned(128)));
static uint32_t fp_source_a[VL] __attribute__((aligned(128)));
static uint32_t fp_source_b[VL] __attribute__((aligned(128)));
static uint8_t source_mask[VLEN_BYTES] __attribute__((aligned(128)));
static uint8_t initial_mask[VLEN_BYTES] __attribute__((aligned(128)));
static uint8_t guard16[VLEN_BYTES] __attribute__((aligned(128)));
static uint8_t guard17[VLEN_BYTES] __attribute__((aligned(128)));
static uint8_t guard18[VLEN_BYTES] __attribute__((aligned(128)));
static uint8_t observed_mask[VLEN_BYTES] __attribute__((aligned(128)));
static uint8_t observed16[VLEN_BYTES] __attribute__((aligned(128)));
static uint8_t observed17[VLEN_BYTES] __attribute__((aligned(128)));
static uint8_t observed18[VLEN_BYTES] __attribute__((aligned(128)));

static void initialize_data(void) {
  for (unsigned index = 0; index < VL; ++index)
    source[index] = (uint16_t)(0x1800u + 19u * index);

  for (unsigned index = 0; index < VL; ++index) {
    fp_source_a[index] = 0x3f800000u + (index << 12);
    fp_source_b[index] = (index & 1) ? 0x40000000u + (index << 12)
                                    : fp_source_a[index];
  }

  for (unsigned index = 0; index < VLEN_BYTES; ++index) {
    initial_mask[index] = (uint8_t)(0xa5u ^ (13u * index));
    guard16[index] = (uint8_t)(0x31u + 17u * index);
    guard17[index] = (uint8_t)(0x72u + 23u * index);
    guard18[index] = (uint8_t)(0xc4u + 29u * index);
    source_mask[index] = 0;
  }
  source_mask[1] = 1u << 1;
}

static int compare_guard(const char *name, const uint8_t *observed,
                         const uint8_t *expected) {
  for (unsigned index = 0; index < VLEN_BYTES; ++index) {
    if (observed[index] != expected[index]) {
      printf("mask compare changed %s byte %d: got=%x expected=%x\n",
             name, index, observed[index], expected[index]);
      return 0;
    }
  }
  return 1;
}

static void check_guards(void) {
  if (!compare_guard("v16", observed16, guard16)) ++num_failed;
  if (!compare_guard("v17", observed17, guard17)) ++num_failed;
  if (!compare_guard("v18", observed18, guard18)) ++num_failed;
}

static void check_mask_pattern(const char *name, unsigned (*expected)(unsigned)) {
  for (unsigned index = 0; index < VL; ++index) {
    unsigned observed = (observed_mask[index >> 3] >> (index & 7)) & 1u;
    if (observed != expected(index)) {
      printf("%s failed at bit %d: got=%d expected=%d\n",
             name, index, observed, expected(index));
      ++num_failed;
      break;
    }
  }
}

static unsigned integer_expected(unsigned index) {
  return source[index] != 0x1839u;
}

static unsigned fp_expected(unsigned index) {
  return index & 1;
}

static unsigned scan_expected(unsigned index) {
  return index < 9;
}

static void test_unaligned_mask_destination(void) {
  const unsigned long scalar = 0x1839u;

  asm volatile(
      "vl1re8.v v15, (%[initial_mask])\n"
      "vl1re8.v v16, (%[guard16])\n"
      "vl1re8.v v17, (%[guard17])\n"
      "vl1re8.v v18, (%[guard18])\n"
      "vsetvli zero, %[vl], e16, m4, ta, ma\n"
      "vle16.v v20, (%[source])\n"
      "vmsne.vx v15, v20, %[scalar]\n"
      "vs1r.v v15, (%[observed_mask])\n"
      "vs1r.v v16, (%[observed16])\n"
      "vs1r.v v17, (%[observed17])\n"
      "vs1r.v v18, (%[observed18])\n"
      "csrr zero, vl\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(VL), [scalar] "r"(scalar), [source] "r"(source),
        [initial_mask] "r"(initial_mask), [guard16] "r"(guard16),
        [guard17] "r"(guard17), [guard18] "r"(guard18),
        [observed_mask] "r"(observed_mask), [observed16] "r"(observed16),
        [observed17] "r"(observed17), [observed18] "r"(observed18)
      : "memory");

  check_mask_pattern("vmsne.vx mask result", integer_expected);
  check_guards();
}

static void test_fp_mask_destination(void) {
  asm volatile(
      "vl1re8.v v15, (%[initial_mask])\n"
      "vl1re8.v v16, (%[guard16])\n"
      "vl1re8.v v17, (%[guard17])\n"
      "vl1re8.v v18, (%[guard18])\n"
      "vsetvli zero, %[vl], e32, m4, ta, ma\n"
      "vle32.v v20, (%[source_a])\n"
      "vle32.v v24, (%[source_b])\n"
      "vmfne.vv v15, v20, v24\n"
      "vs1r.v v15, (%[observed_mask])\n"
      "vs1r.v v16, (%[observed16])\n"
      "vs1r.v v17, (%[observed17])\n"
      "vs1r.v v18, (%[observed18])\n"
      "csrr zero, vl\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(VL), [source_a] "r"(fp_source_a),
        [source_b] "r"(fp_source_b), [initial_mask] "r"(initial_mask),
        [guard16] "r"(guard16), [guard17] "r"(guard17),
        [guard18] "r"(guard18), [observed_mask] "r"(observed_mask),
        [observed16] "r"(observed16), [observed17] "r"(observed17),
        [observed18] "r"(observed18)
      : "memory");

  check_mask_pattern("vmfne.vv mask result", fp_expected);
  check_guards();
}

static void test_mask_scan_destination(void) {
  asm volatile(
      "vl1re8.v v14, (%[source_mask])\n"
      "vl1re8.v v15, (%[initial_mask])\n"
      "vl1re8.v v16, (%[guard16])\n"
      "vl1re8.v v17, (%[guard17])\n"
      "vl1re8.v v18, (%[guard18])\n"
      "vsetvli zero, %[vl], e8, m8, ta, ma\n"
      "vmsbf.m v15, v14\n"
      "vs1r.v v15, (%[observed_mask])\n"
      "vs1r.v v16, (%[observed16])\n"
      "vs1r.v v17, (%[observed17])\n"
      "vs1r.v v18, (%[observed18])\n"
      "csrr zero, vl\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(VL), [source_mask] "r"(source_mask),
        [initial_mask] "r"(initial_mask), [guard16] "r"(guard16),
        [guard17] "r"(guard17), [guard18] "r"(guard18),
        [observed_mask] "r"(observed_mask), [observed16] "r"(observed16),
        [observed17] "r"(observed17), [observed18] "r"(observed18)
      : "memory");

  check_mask_pattern("vmsbf.m mask result", scan_expected);
  check_guards();
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  enable_fp();
  initialize_data();
  test_unaligned_mask_destination();
  test_fp_mask_destination();
  test_mask_scan_destination();
  EXIT_CHECK();
}
