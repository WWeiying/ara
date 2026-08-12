// Check target-memory state immediately after representative vector stores.

#include "vector_macros.h"

#define ELEMENTS 8
#define CROSS_ELEMENTS 79
#define CROSS_VSTART 34
#define CROSS_SENTINEL 0xdeadbeefU
#define ORDERED_ELEMENTS 79

static uint32_t source_a[ELEMENTS] __attribute__((aligned(128))) = {
    0x01234567, 0x89abcdef, 0, 1, 0xffffffff, 0x80000000, 0x55aa55aa, 0xaa55aa55};
static uint32_t source_b[ELEMENTS] __attribute__((aligned(128))) = {
    8, 7, 6, 5, 4, 3, 2, 1};
static uint32_t source_poison[ELEMENTS] __attribute__((aligned(128))) = {
    0xf0010000, 0xf0010001, 0xf0010002, 0xf0010003,
    0xf0010004, 0xf0010005, 0xf0010006, 0xf0010007};
static uint32_t unit_target[ELEMENTS] __attribute__((aligned(128)));
static uint32_t strided_target[ELEMENTS * 2] __attribute__((aligned(128)));
static uint32_t indexed_target[ELEMENTS * 2] __attribute__((aligned(128)));
static uint32_t segment_target[ELEMENTS * 2] __attribute__((aligned(128)));
static uint32_t segment_m4_target[ELEMENTS * 2] __attribute__((aligned(128)));
static uint32_t indices[ELEMENTS] __attribute__((aligned(128))) = {
    28, 0, 52, 8, 44, 16, 36, 24};
static uint32_t cross_source[CROSS_ELEMENTS] __attribute__((aligned(128)));
static uint16_t cross_head[64] __attribute__((aligned(128)));
static uint32_t cross_target[CROSS_ELEMENTS] __attribute__((aligned(128)));
static uint32_t cross_zero_target[CROSS_ELEMENTS] __attribute__((aligned(128)));
static uint16_t ordered_source[ORDERED_ELEMENTS] __attribute__((aligned(128)));
static uint16_t ordered_indices[ORDERED_ELEMENTS] __attribute__((aligned(128)));
static uint16_t ordered_target __attribute__((aligned(128)));

static void wait_for_store(void) {
  unsigned long vl;
  asm volatile("csrr %0, vl\n fence rw, rw" : "=r"(vl) :: "memory");
}

static int compare_word(const char *name, unsigned index, uint32_t observed,
                        uint32_t expected) {
  if (observed == expected)
    return 1;
  printf("%s failed at %d: got=%x expected=%x\n", name, index, observed, expected);
  ++num_failed;
  return 0;
}

static void test_unit_store(void) {
  asm volatile(
      "vsetvli zero, %[vl], e32, m1, tu, mu\n"
      "vle32.v v8, (%[source])\n"
      "vse32.v v8, (%[target])\n"
      :
      : [vl] "r"(ELEMENTS), [source] "r"(source_a), [target] "r"(unit_target)
      : "memory");
  wait_for_store();
  for (unsigned index = 0; index < ELEMENTS; ++index)
    if (!compare_word("unit store", index, unit_target[index], source_a[index]))
      break;
}

static void test_strided_store(void) {
  for (unsigned index = 0; index < ELEMENTS * 2; ++index)
    strided_target[index] = 0xdeadbeef;
  long stride = 8;
  asm volatile(
      "vsetvli zero, %[vl], e32, m1, tu, mu\n"
      "vle32.v v8, (%[source])\n"
      "vsse32.v v8, (%[target]), %[stride]\n"
      :
      : [vl] "r"(ELEMENTS), [source] "r"(source_a),
        [target] "r"(strided_target), [stride] "r"(stride)
      : "memory");
  wait_for_store();
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    if (!compare_word("strided store data", index, strided_target[index * 2],
                      source_a[index]))
      break;
    if (!compare_word("strided store hole", index, strided_target[index * 2 + 1],
                      0xdeadbeef))
      break;
  }
}

static void test_indexed_store(void) {
  for (unsigned index = 0; index < ELEMENTS * 2; ++index)
    indexed_target[index] = 0xdeadbeef;
  asm volatile(
      "vsetvli zero, %[vl], e32, m1, tu, mu\n"
      "vle32.v v8, (%[source])\n"
      "vle32.v v9, (%[indices])\n"
      "vsuxei32.v v8, (%[target]), v9\n"
      :
      : [vl] "r"(ELEMENTS), [source] "r"(source_a), [indices] "r"(indices),
        [target] "r"(indexed_target)
      : "memory");
  wait_for_store();
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    unsigned destination = indices[index] / sizeof(uint32_t);
    if (!compare_word("indexed store", index, indexed_target[destination],
                      source_a[index]))
      break;
  }
}

static void test_segment_store(void) {
  asm volatile(
      "vsetvli zero, %[vl], e32, m1, tu, mu\n"
      "vle32.v v8, (%[a])\n"
      "vle32.v v9, (%[b])\n"
      "vsseg2e32.v v8, (%[target])\n"
      :
      : [vl] "r"(ELEMENTS), [a] "r"(source_a), [b] "r"(source_b),
        [target] "r"(segment_target)
      : "memory");
  wait_for_store();
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    if (!compare_word("segment store field 0", index, segment_target[2 * index],
                      source_a[index]))
      break;
    if (!compare_word("segment store field 1", index, segment_target[2 * index + 1],
                      source_b[index]))
      break;
  }
}

static void test_segment_store_m4(void) {
  asm volatile(
      "vsetvli zero, %[vl], e32, m1, tu, mu\n"
      "vle32.v v9, (%[poison])\n"
      "vsetvli zero, %[vl], e32, m4, tu, mu\n"
      "vle32.v v8, (%[a])\n"
      "vle32.v v12, (%[b])\n"
      "vsseg2e32.v v8, (%[target])\n"
      :
      : [vl] "r"(ELEMENTS), [poison] "r"(source_poison), [a] "r"(source_a),
        [b] "r"(source_b),
        [target] "r"(segment_m4_target)
      : "memory");
  wait_for_store();
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    if (!compare_word("segment m4 field 0", index,
                      segment_m4_target[2 * index], source_a[index]))
      break;
    if (!compare_word("segment m4 field 1", index,
                      segment_m4_target[2 * index + 1], source_b[index]))
      break;
  }
}

static void test_unit_store_cross_register_layout(void) {
  for (unsigned index = 0; index < CROSS_ELEMENTS; ++index) {
    cross_source[index] = 0x41000000U + index;
    cross_target[index] = CROSS_SENTINEL;
    cross_zero_target[index] = CROSS_SENTINEL;
  }
  for (unsigned index = 0; index < 64; ++index)
    cross_head[index] = 0x5200U + index;

  asm volatile(
      "vsetvli zero, %[vl], e32, m8, tu, mu\n"
      "vle32.v v0, (%[source])\n"
      // Give the inactive group head a different physical layout. The active
      // e32 interval begins in v1 and must not inherit v0's old EEW tag.
      "vsetvli zero, %[head_vl], e16, m1, tu, mu\n"
      "vle16.v v0, (%[head])\n"
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "csrw vstart, %[vstart]\n"
      "vse32.v v0, (%[target])\n"
      :
      : [vl] "r"(CROSS_ELEMENTS), [head_vl] "r"(64),
        [vstart] "r"(CROSS_VSTART), [source] "r"(cross_source),
        [head] "r"(cross_head), [target] "r"(cross_target)
      : "memory");
  wait_for_store();

  for (unsigned index = 0; index < CROSS_ELEMENTS; ++index) {
    uint32_t expected =
        index < CROSS_VSTART ? CROSS_SENTINEL : cross_source[index];
    if (!compare_word("unit store cross-register layout", index,
                      cross_target[index], expected))
      break;
  }

  asm volatile(
      "vsetvli zero, %[vl], e32, m8, tu, mu\n"
      "vle32.v v0, (%[source])\n"
      // Preserve v0's architectural bytes while assigning the group head an
      // EW16 physical layout; v1-v7 retain EW32 layouts.
      "vsetvli zero, %[head_vl], e16, m1, tu, mu\n"
      "vle16.v v0, (%[source])\n"
      "vsetvli zero, %[vl], e32, m8, tu, mu\n"
      "vse32.v v0, (%[target])\n"
      :
      : [vl] "r"(CROSS_ELEMENTS), [head_vl] "r"(64),
        [source] "r"(cross_source), [target] "r"(cross_zero_target)
      : "memory");
  wait_for_store();

  for (unsigned index = 0; index < CROSS_ELEMENTS; ++index) {
    if (!compare_word("unit store mixed layout at vstart zero", index,
                      cross_zero_target[index], cross_source[index]))
      break;
  }
}

static void test_ordered_indexed_store_mixed_source_layout(void) {
  for (unsigned index = 0; index < ORDERED_ELEMENTS; ++index) {
    ordered_source[index] = 0x4000U + index;
    ordered_indices[index] = 0;
  }
  ordered_target = 0xdeadU;

  asm volatile(
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vle16.v v24, (%[source])\n"
      // Preserve v24's architectural bytes but assign its physical register
      // an EW8 layout. v25-v27 retain EW16 layouts.
      "vsetvli zero, %[head_bytes], e8, m1, tu, mu\n"
      "vle8.v v24, (%[source])\n"
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vle16.v v28, (%[indices])\n"
      // Every element targets the same halfword. Ordered indexed stores must
      // leave the value of the final logical element in memory.
      "vsoxei16.v v24, (%[target]), v28\n"
      :
      : [vl] "r"(ORDERED_ELEMENTS), [head_bytes] "r"(128),
        [source] "r"(ordered_source), [indices] "r"(ordered_indices),
        [target] "r"(&ordered_target)
      : "memory");
  wait_for_store();

  compare_word("ordered indexed store mixed source layout", 0,
               ordered_target, ordered_source[ORDERED_ELEMENTS - 1]);
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  test_unit_store();
  test_strided_store();
  test_indexed_store();
  test_segment_store();
  test_segment_store_m4();
  test_unit_store_cross_register_layout();
  test_ordered_indexed_store_mixed_source_layout();
  EXIT_CHECK();
}
