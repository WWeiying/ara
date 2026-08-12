// Check segment field register spacing for EMUL greater than one.

#include "vector_macros.h"

#define ELEMENTS 16
#define SENTINEL 0xdeadbeefU
#define SEGMENT_ELEMENTS 54
#define REGISTER_HALFWORDS 64
#define STRIDED5_ELEMENTS 4
#define STRIDED5_FIELDS 5
#define STRIDED5_ROW_WORDS 10
#define STRIDED8_ELEMENTS 16
#define STRIDED8_FIELDS 8
#define STRIDED8_ROW_WORDS 14
#define MIXED_E8_ELEMENTS 5
#define MIXED_E8_STRIDE 57
#define MIXED_E8_TARGET_BYTES \
  ((MIXED_E8_ELEMENTS - 1) * MIXED_E8_STRIDE + 2)
#define INDEXED_E16_ELEMENTS 79
#define INDEXED_E16_SOURCE_BYTES 0x10000

static uint32_t field_a[ELEMENTS] __attribute__((aligned(128)));
static uint32_t field_b[ELEMENTS] __attribute__((aligned(128)));
static uint32_t poison[ELEMENTS] __attribute__((aligned(128)));
static uint32_t interleaved[ELEMENTS * 2] __attribute__((aligned(128)));
static uint32_t indices[ELEMENTS] __attribute__((aligned(128)));
static uint8_t even_mask[ELEMENTS / 8] __attribute__((aligned(128))) = {0x55, 0x55};
static uint32_t output_a[ELEMENTS] __attribute__((aligned(128)));
static uint32_t output_b[ELEMENTS] __attribute__((aligned(128)));
static uint32_t indexed_target[ELEMENTS * 2] __attribute__((aligned(128)));
static uint32_t strided_target[ELEMENTS * 2] __attribute__((aligned(128)));
static uint16_t mixed_layout_old_a[REGISTER_HALFWORDS] __attribute__((aligned(128)));
static uint16_t mixed_layout_old_b[REGISTER_HALFWORDS] __attribute__((aligned(128)));
static uint16_t mixed_layout_source[SEGMENT_ELEMENTS * 2] __attribute__((aligned(128)));
static uint8_t mixed_layout_mask[(SEGMENT_ELEMENTS + 7) / 8] __attribute__((aligned(128)));
static uint16_t mixed_layout_output_a[REGISTER_HALFWORDS] __attribute__((aligned(128)));
static uint16_t mixed_layout_output_b[REGISTER_HALFWORDS] __attribute__((aligned(128)));
static uint64_t strided5_source[STRIDED5_ELEMENTS][STRIDED5_ROW_WORDS]
    __attribute__((aligned(128)));
static uint64_t strided5_initial[STRIDED5_FIELDS][STRIDED5_ELEMENTS]
    __attribute__((aligned(128)));
static uint64_t strided5_output[STRIDED5_FIELDS][STRIDED5_ELEMENTS]
    __attribute__((aligned(128)));
static uint8_t strided5_mask[1] __attribute__((aligned(128))) = {0x09};
static uint64_t strided8_fields[STRIDED8_FIELDS][STRIDED8_ELEMENTS]
    __attribute__((aligned(128)));
static uint64_t strided8_target[STRIDED8_ELEMENTS][STRIDED8_ROW_WORDS]
    __attribute__((aligned(128)));
static uint8_t mixed_e8_field0[128] __attribute__((aligned(128)));
static uint8_t mixed_e8_field1[128] __attribute__((aligned(128)));
static uint8_t mixed_e8_target[MIXED_E8_TARGET_BYTES]
    __attribute__((aligned(128)));
static uint32_t indexed4_source[ELEMENTS][4] __attribute__((aligned(128)));
static uint32_t indexed4_target[ELEMENTS][4] __attribute__((aligned(128)));
static uint32_t indexed4_output[4][ELEMENTS] __attribute__((aligned(128)));
static uint64_t indexed4_offsets[ELEMENTS] __attribute__((aligned(128)));
static uint8_t indexed_e16_source[INDEXED_E16_SOURCE_BYTES]
    __attribute__((aligned(4096)));
static uint32_t indexed_e16_offsets[INDEXED_E16_ELEMENTS]
    __attribute__((aligned(128)));
static uint16_t indexed_e16_output_a[INDEXED_E16_ELEMENTS]
    __attribute__((aligned(128)));
static uint16_t indexed_e16_output_b[INDEXED_E16_ELEMENTS]
    __attribute__((aligned(128)));

static void initialize_data(void) {
  for (unsigned i = 0; i < ELEMENTS; ++i) {
    field_a[i] = 0x1000 + i;
    field_b[i] = 0x2000 + i;
    poison[i] = 0xf0010000 + i;
    interleaved[2 * i] = field_a[i];
    interleaved[2 * i + 1] = field_b[i];
    indices[i] = 2 * i * sizeof(uint32_t);
  }
  for (unsigned i = 0; i < REGISTER_HALFWORDS; ++i) {
    mixed_layout_old_a[i] = 0xa000U + i;
    mixed_layout_old_b[i] = 0xb000U + i;
  }
  for (unsigned i = 0; i < SEGMENT_ELEMENTS; ++i) {
    mixed_layout_source[2 * i] = 0x1000U + i;
    mixed_layout_source[2 * i + 1] = 0x2000U + i;
    if ((i & 1U) == 0)
      mixed_layout_mask[i / 8] |= 1U << (i % 8);
  }
  for (unsigned i = 0; i < STRIDED5_ELEMENTS; ++i) {
    for (unsigned field = 0; field < STRIDED5_FIELDS; ++field) {
      strided5_source[i][field] =
          0x8100000000000000UL + 0x100UL * i + field;
      strided5_initial[field][i] =
          0xa500000000000000UL + 0x100UL * field + i;
    }
    for (unsigned field = STRIDED5_FIELDS; field < STRIDED5_ROW_WORDS;
         ++field)
      strided5_source[i][field] = 0xcc00000000000000UL + 0x100UL * i + field;
  }
  for (unsigned i = 0; i < STRIDED8_ELEMENTS; ++i) {
    for (unsigned field = 0; field < STRIDED8_FIELDS; ++field)
      strided8_fields[field][i] =
          0x9100000000000000UL + 0x10000UL * field + i;
    for (unsigned word = 0; word < STRIDED8_ROW_WORDS; ++word)
      strided8_target[i][word] = 0xdeadbeefcafef00dUL;
  }
  for (unsigned i = 0; i < 128; ++i) {
    mixed_e8_field0[i] = 0x20U + i;
    mixed_e8_field1[i] = 0x90U + i;
  }
  for (unsigned i = 0; i < ELEMENTS; ++i) {
    indexed4_offsets[i] = i * 4 * sizeof(uint32_t);
    for (unsigned field = 0; field < 4; ++field) {
      indexed4_source[i][field] = 0x51000000U + 0x10000U * field + i;
      indexed4_target[i][field] = SENTINEL;
    }
  }
  for (unsigned i = 0; i < INDEXED_E16_ELEMENTS; ++i) {
    unsigned offset = 4 * i;
    if (i == 33)
      offset = 4094;
    else if (i == 34)
      offset = 0x400a;
    indexed_e16_offsets[i] = offset;
    *(uint16_t *)&indexed_e16_source[offset] = 0x4000U + i;
    *(uint16_t *)&indexed_e16_source[offset + sizeof(uint16_t)] = 0x5000U + i;
  }
}

static void wait_for_memory(void) {
  unsigned long vl;
  asm volatile("csrr %0, vl\n fence rw, rw" : "=r"(vl) :: "memory");
}

static void clear_words(uint32_t *target, unsigned words) {
  for (unsigned i = 0; i < words; ++i)
    target[i] = SENTINEL;
}

static void check_word(const char *name, unsigned index, uint32_t observed,
                       uint32_t expected) {
  if (observed == expected)
    return;
  printf("%s failed at %d: got=%x expected=%x\n", name, index, observed,
         expected);
  ++num_failed;
}

static void check_dword(const char *name, unsigned index, uint64_t observed,
                        uint64_t expected) {
  if (observed == expected)
    return;
  printf("%s failed at %d: got=%lx expected=%lx\n", name, index, observed,
         expected);
  ++num_failed;
}

static void check_fields(const char *name) {
  for (unsigned i = 0; i < ELEMENTS; ++i) {
    check_word(name, 2 * i, output_a[i], field_a[i]);
    check_word(name, 2 * i + 1, output_b[i], field_b[i]);
  }
}

static void test_unit_segment_load_m4(void) {
  asm volatile(
      "vsetvli zero, %[vl], e32, m1, tu, mu\n"
      "vle32.v v12, (%[poison])\n"
      "vsetvli zero, %[vl], e32, m4, tu, mu\n"
      "vlseg2e32.v v8, (%[source])\n"
      "vse32.v v8, (%[out_a])\n"
      "vse32.v v12, (%[out_b])\n"
      :
      : [vl] "r"(ELEMENTS), [poison] "r"(poison), [source] "r"(interleaved),
        [out_a] "r"(output_a), [out_b] "r"(output_b)
      : "memory");
  wait_for_memory();
  check_fields("unit segment load m4");
}

static void test_unit_segment_load_vstart_m4(void) {
  const unsigned long vstart = 1;

  asm volatile(
      "vsetvli zero, %[vl], e32, m1, tu, mu\n"
      "vle32.v v8, (%[poison])\n"
      "vle32.v v12, (%[poison])\n"
      "vsetvli zero, %[vl], e32, m4, tu, mu\n"
      "csrw vstart, %[vstart]\n"
      "vlseg2e32.v v8, (%[source])\n"
      "vse32.v v8, (%[out_a])\n"
      "vse32.v v12, (%[out_b])\n"
      :
      : [vl] "r"(ELEMENTS), [vstart] "r"(vstart), [poison] "r"(poison),
        [source] "r"(interleaved), [out_a] "r"(output_a),
        [out_b] "r"(output_b)
      : "memory");
  wait_for_memory();

  for (unsigned i = 0; i < ELEMENTS; ++i) {
    const uint32_t expected_a = i < vstart ? poison[i] : field_a[i];
    const uint32_t expected_b = i < vstart ? poison[i] : field_b[i];
    check_word("unit segment load vstart m4 field 0", i, output_a[i],
               expected_a);
    check_word("unit segment load vstart m4 field 1", i, output_b[i],
               expected_b);
  }
}

static void test_masked_segment_load_preserves_mixed_layout(void) {
  const unsigned long initial_vl = REGISTER_HALFWORDS / 4;

  asm volatile(
      // Load the raw destination bits through an EW64 view, then consume the
      // same registers as two EW16 segment fields. Masked-off and tail bits
      // must survive the internal physical-layout conversion.
      "vsetvli zero, %[initial_vl], e64, m1, tu, mu\n"
      "vle64.v v8, (%[old_a])\n"
      "vle64.v v9, (%[old_b])\n"
      "vsetvli zero, %[segment_vl], e64, m4, tu, mu\n"
      "vlm.v v0, (%[mask])\n"
      "vlseg2e16.v v8, (%[source]), v0.t\n"
      "vsetvli zero, %[output_vl], e16, m1, tu, mu\n"
      "vse16.v v8, (%[out_a])\n"
      "vse16.v v9, (%[out_b])\n"
      :
      : [initial_vl] "r"(initial_vl), [segment_vl] "r"(SEGMENT_ELEMENTS),
        [output_vl] "r"(REGISTER_HALFWORDS), [old_a] "r"(mixed_layout_old_a),
        [old_b] "r"(mixed_layout_old_b), [mask] "r"(mixed_layout_mask),
        [source] "r"(mixed_layout_source), [out_a] "r"(mixed_layout_output_a),
        [out_b] "r"(mixed_layout_output_b)
      : "memory");
  wait_for_memory();

  for (unsigned i = 0; i < REGISTER_HALFWORDS; ++i) {
    const int active = i < SEGMENT_ELEMENTS && ((i & 1U) == 0);
    const uint16_t expected_a = active ? mixed_layout_source[2 * i]
                                       : mixed_layout_old_a[i];
    const uint16_t expected_b = active ? mixed_layout_source[2 * i + 1]
                                       : mixed_layout_old_b[i];
    check_word("masked segment load mixed layout field 0", i,
               mixed_layout_output_a[i], expected_a);
    check_word("masked segment load mixed layout field 1", i,
               mixed_layout_output_b[i], expected_b);
  }
}

static void test_indexed_segment_load_m4(void) {
  asm volatile(
      "vsetvli zero, %[vl], e32, m1, tu, mu\n"
      "vle32.v v12, (%[poison])\n"
      "vsetvli zero, %[vl], e32, m4, tu, mu\n"
      "vle32.v v16, (%[indices])\n"
      "vluxseg2ei32.v v8, (%[source]), v16\n"
      "vse32.v v8, (%[out_a])\n"
      "vse32.v v12, (%[out_b])\n"
      :
      : [vl] "r"(ELEMENTS), [poison] "r"(poison), [indices] "r"(indices),
        [source] "r"(interleaved), [out_a] "r"(output_a),
        [out_b] "r"(output_b)
      : "memory");
  wait_for_memory();
  check_fields("indexed segment load m4");
}

static void test_indexed_segment_load_e16_m4_page_boundary(void) {
  asm volatile(
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vle32.v v0, (%[indices])\n"
      "vloxseg2ei32.v v8, (%[source]), v0\n"
      "vse16.v v8, (%[out_a])\n"
      "vse16.v v12, (%[out_b])\n"
      :
      : [vl] "r"(INDEXED_E16_ELEMENTS),
        [indices] "r"(indexed_e16_offsets), [source] "r"(indexed_e16_source),
        [out_a] "r"(indexed_e16_output_a),
        [out_b] "r"(indexed_e16_output_b)
      : "memory");
  wait_for_memory();

  for (unsigned i = 0; i < INDEXED_E16_ELEMENTS; ++i) {
    check_word("indexed segment e16 m4 page boundary field 0", i,
               indexed_e16_output_a[i], 0x4000U + i);
    check_word("indexed segment e16 m4 page boundary field 1", i,
               indexed_e16_output_b[i], 0x5000U + i);
  }
}

static void test_indexed_segment_v8_decode(void) {
  asm volatile(
      "vsetvli zero, %[vl], e64, m4, tu, mu\n"
      "vle64.v v8, (%[indices])\n"
      "vsetvli zero, %[vl], e32, m2, tu, mu\n"
      "vloxseg4ei64.v v0, (%[source]), v8\n"
      "vse32.v v0, (%[out0])\n"
      "vse32.v v2, (%[out1])\n"
      "vse32.v v4, (%[out2])\n"
      "vse32.v v6, (%[out3])\n"
      "vsoxseg4ei64.v v0, (%[target]), v8\n"
      :
      : [vl] "r"(ELEMENTS), [indices] "r"(indexed4_offsets),
        [source] "r"(indexed4_source), [target] "r"(indexed4_target),
        [out0] "r"(indexed4_output[0]), [out1] "r"(indexed4_output[1]),
        [out2] "r"(indexed4_output[2]), [out3] "r"(indexed4_output[3])
      : "memory");
  wait_for_memory();

  for (unsigned i = 0; i < ELEMENTS; ++i) {
    for (unsigned field = 0; field < 4; ++field) {
      const unsigned index = field * ELEMENTS + i;
      check_word("indexed segment v8 load", index,
                 indexed4_output[field][i], indexed4_source[i][field]);
      check_word("indexed segment v8 store", index,
                 indexed4_target[i][field], indexed4_source[i][field]);
    }
  }
}

static void test_masked_indexed_segment_store_m4(void) {
  clear_words(indexed_target, ELEMENTS * 2);
  asm volatile(
      "vsetvli zero, %[vl], e32, m1, tu, mu\n"
      "vle32.v v9, (%[poison])\n"
      "vsetvli zero, %[vl], e32, m4, tu, mu\n"
      "vle32.v v8, (%[field_a])\n"
      "vle32.v v12, (%[field_b])\n"
      "vle32.v v16, (%[indices])\n"
      "vlm.v v0, (%[mask])\n"
      "vsuxseg2ei32.v v8, (%[target]), v16, v0.t\n"
      :
      : [vl] "r"(ELEMENTS), [poison] "r"(poison), [field_a] "r"(field_a),
        [field_b] "r"(field_b), [indices] "r"(indices),
        [mask] "r"(even_mask), [target] "r"(indexed_target)
      : "memory");
  wait_for_memory();
  for (unsigned i = 0; i < ELEMENTS; ++i) {
    uint32_t expected_a = (i & 1) ? SENTINEL : field_a[i];
    uint32_t expected_b = (i & 1) ? SENTINEL : field_b[i];
    check_word("indexed segment store m4", 2 * i, indexed_target[2 * i],
               expected_a);
    check_word("indexed segment store m4", 2 * i + 1,
               indexed_target[2 * i + 1], expected_b);
  }
}

static void test_masked_indexed_segment_store_vstart_m4(void) {
  const unsigned long vstart = 5;

  clear_words(indexed_target, ELEMENTS * 2);
  asm volatile(
      "vsetvli zero, %[vl], e32, m1, tu, mu\n"
      "vle32.v v9, (%[poison])\n"
      "vsetvli zero, %[vl], e32, m4, tu, mu\n"
      "vle32.v v8, (%[field_a])\n"
      "vle32.v v12, (%[field_b])\n"
      "vle32.v v16, (%[indices])\n"
      "vlm.v v0, (%[mask])\n"
      "csrw vstart, %[vstart]\n"
      "vsuxseg2ei32.v v8, (%[target]), v16, v0.t\n"
      :
      : [vl] "r"(ELEMENTS), [vstart] "r"(vstart),
        [poison] "r"(poison), [field_a] "r"(field_a),
        [field_b] "r"(field_b), [indices] "r"(indices),
        [mask] "r"(even_mask), [target] "r"(indexed_target)
      : "memory");
  wait_for_memory();
  for (unsigned i = 0; i < ELEMENTS; ++i) {
    uint32_t expected_a = (i < vstart || (i & 1)) ? SENTINEL : field_a[i];
    uint32_t expected_b = (i < vstart || (i & 1)) ? SENTINEL : field_b[i];
    check_word("indexed segment store vstart m4", 2 * i,
               indexed_target[2 * i], expected_a);
    check_word("indexed segment store vstart m4", 2 * i + 1,
               indexed_target[2 * i + 1], expected_b);
  }
}

static void test_strided_segment_store_m4(void) {
  clear_words(strided_target, ELEMENTS * 2);
  long stride = 8;
  asm volatile(
      "vsetvli zero, %[vl], e32, m1, tu, mu\n"
      "vle32.v v9, (%[poison])\n"
      "vsetvli zero, %[vl], e32, m4, tu, mu\n"
      "vle32.v v8, (%[field_a])\n"
      "vle32.v v12, (%[field_b])\n"
      "vssseg2e32.v v8, (%[target]), %[stride]\n"
      :
      : [vl] "r"(ELEMENTS), [poison] "r"(poison), [field_a] "r"(field_a),
        [field_b] "r"(field_b), [target] "r"(strided_target),
        [stride] "r"(stride)
      : "memory");
  wait_for_memory();
  for (unsigned i = 0; i < ELEMENTS; ++i) {
    check_word("strided segment store m4", 2 * i, strided_target[2 * i],
               field_a[i]);
    check_word("strided segment store m4", 2 * i + 1,
               strided_target[2 * i + 1], field_b[i]);
  }
}

static void test_strided_segment_store_mixed_layout_e8_vstart(void) {
  const unsigned long vl = MIXED_E8_ELEMENTS;
  const unsigned long vstart = 2;
  const unsigned long stride = MIXED_E8_STRIDE;

  for (unsigned i = 0; i < MIXED_E8_TARGET_BYTES; ++i)
    mixed_e8_target[i] = 0xa5;

  asm volatile(
      "vsetivli zero, 16, e8, m1, tu, mu\n"
      "vle8.v v2, (%[field0])\n"
      // Keep identical architectural bytes in a different physical layout.
      "vsetivli zero, 16, e64, m1, tu, mu\n"
      "vle64.v v3, (%[field1])\n"
      "vsetvli zero, %[vl], e32, mf2, tu, mu\n"
      "csrw vstart, %[vstart]\n"
      "vssseg2e8.v v2, (%[target]), %[stride]\n"
      :
      : [vl] "r"(vl), [vstart] "r"(vstart), [stride] "r"(stride),
        [field0] "r"(mixed_e8_field0), [field1] "r"(mixed_e8_field1),
        [target] "r"(mixed_e8_target)
      : "memory");
  wait_for_memory();

  for (unsigned i = 0; i < MIXED_E8_ELEMENTS; ++i) {
    const uint8_t expected0 = i < vstart ? 0xa5 : mixed_e8_field0[i];
    const uint8_t expected1 = i < vstart ? 0xa5 : mixed_e8_field1[i];
    check_word("strided segment store mixed e8 vstart field 0", i,
               mixed_e8_target[i * MIXED_E8_STRIDE], expected0);
    check_word("strided segment store mixed e8 vstart field 1", i,
               mixed_e8_target[i * MIXED_E8_STRIDE + 1], expected1);
  }
}

static void test_masked_strided_segment_load_nf5_e64(void) {
  const unsigned long stride = STRIDED5_ROW_WORDS * sizeof(uint64_t);

  asm volatile(
      "vsetivli zero, 4, e64, m1, tu, mu\n"
      "vle64.v v5, (%[old0])\n"
      "vle64.v v6, (%[old1])\n"
      "vle64.v v7, (%[old2])\n"
      "vle64.v v8, (%[old3])\n"
      "vle64.v v9, (%[old4])\n"
      "vlm.v v0, (%[mask])\n"
      "vlsseg5e64.v v5, (%[source]), %[stride], v0.t\n"
      "vse64.v v5, (%[out0])\n"
      "vse64.v v6, (%[out1])\n"
      "vse64.v v7, (%[out2])\n"
      "vse64.v v8, (%[out3])\n"
      "vse64.v v9, (%[out4])\n"
      :
      : [old0] "r"(strided5_initial[0]), [old1] "r"(strided5_initial[1]),
        [old2] "r"(strided5_initial[2]), [old3] "r"(strided5_initial[3]),
        [old4] "r"(strided5_initial[4]), [mask] "r"(strided5_mask),
        [source] "r"(strided5_source), [stride] "r"(stride),
        [out0] "r"(strided5_output[0]), [out1] "r"(strided5_output[1]),
        [out2] "r"(strided5_output[2]), [out3] "r"(strided5_output[3]),
        [out4] "r"(strided5_output[4])
      : "memory");
  wait_for_memory();

  for (unsigned field = 0; field < STRIDED5_FIELDS; ++field) {
    for (unsigned i = 0; i < STRIDED5_ELEMENTS; ++i) {
      const uint64_t expected = (i == 0 || i == 3)
                                  ? strided5_source[i][field]
                                  : strided5_initial[field][i];
      check_dword("masked strided segment load nf5 e64",
                  field * STRIDED5_ELEMENTS + i,
                  strided5_output[field][i], expected);
    }
  }
}

static void test_strided_segment_store_nf8_e64(void) {
  const unsigned long stride = STRIDED8_ROW_WORDS * sizeof(uint64_t);

  asm volatile(
      "vsetivli zero, 16, e64, m1, tu, mu\n"
      "vle64.v v9, (%[field0])\n"
      "vle64.v v10, (%[field1])\n"
      "vle64.v v11, (%[field2])\n"
      "vle64.v v12, (%[field3])\n"
      "vle64.v v13, (%[field4])\n"
      "vle64.v v14, (%[field5])\n"
      "vle64.v v15, (%[field6])\n"
      "vle64.v v16, (%[field7])\n"
      "vssseg8e64.v v9, (%[target]), %[stride]\n"
      :
      : [field0] "r"(strided8_fields[0]), [field1] "r"(strided8_fields[1]),
        [field2] "r"(strided8_fields[2]), [field3] "r"(strided8_fields[3]),
        [field4] "r"(strided8_fields[4]), [field5] "r"(strided8_fields[5]),
        [field6] "r"(strided8_fields[6]), [field7] "r"(strided8_fields[7]),
        [target] "r"(strided8_target), [stride] "r"(stride)
      : "memory");
  wait_for_memory();

  for (unsigned i = 0; i < STRIDED8_ELEMENTS; ++i) {
    for (unsigned field = 0; field < STRIDED8_FIELDS; ++field)
      check_dword("strided segment store nf8 e64",
                  i * STRIDED8_ROW_WORDS + field,
                  strided8_target[i][field], strided8_fields[field][i]);
    for (unsigned word = STRIDED8_FIELDS; word < STRIDED8_ROW_WORDS; ++word)
      check_dword("strided segment store nf8 e64 gap",
                  i * STRIDED8_ROW_WORDS + word,
                  strided8_target[i][word], 0xdeadbeefcafef00dUL);
  }
}

static void test_strided_segment_store_nf8_e64_mf2(void) {
  const unsigned long stride = STRIDED8_ROW_WORDS * sizeof(uint64_t);

  for (unsigned i = 0; i < STRIDED8_ELEMENTS; ++i)
    for (unsigned word = 0; word < STRIDED8_ROW_WORDS; ++word)
      strided8_target[i][word] = 0xdeadbeefcafef00dUL;

  asm volatile(
      "vsetivli zero, 4, e64, m1, tu, mu\n"
      "vle64.v v9,  (%[field0])\n"
      "vle64.v v10, (%[field1])\n"
      "vle64.v v11, (%[field2])\n"
      "vle64.v v12, (%[field3])\n"
      "vle64.v v13, (%[field4])\n"
      "vle64.v v14, (%[field5])\n"
      "vle64.v v15, (%[field6])\n"
      "vle64.v v16, (%[field7])\n"
      "vsetivli zero, 4, e32, mf2, tu, mu\n"
      "vssseg8e64.v v9, (%[target]), %[stride]\n"
      :
      : [field0] "r"(strided8_fields[0]),
        [field1] "r"(strided8_fields[1]),
        [field2] "r"(strided8_fields[2]),
        [field3] "r"(strided8_fields[3]),
        [field4] "r"(strided8_fields[4]),
        [field5] "r"(strided8_fields[5]),
        [field6] "r"(strided8_fields[6]),
        [field7] "r"(strided8_fields[7]), [target] "r"(strided8_target),
        [stride] "r"(stride)
      : "memory");
  wait_for_memory();

  for (unsigned i = 0; i < STRIDED8_ELEMENTS; ++i) {
    for (unsigned word = 0; word < STRIDED8_ROW_WORDS; ++word) {
      const uint64_t expected =
          i < 4 && word < STRIDED8_FIELDS
              ? strided8_fields[word][i]
              : 0xdeadbeefcafef00dUL;
      check_dword("strided segment store nf8 e64 mf2",
                  i * STRIDED8_ROW_WORDS + word,
                  strided8_target[i][word], expected);
    }
  }
}

static void test_strided_segment_store_nf8_e64_from_e32_layout(void) {
  const unsigned long stride = STRIDED8_ROW_WORDS * sizeof(uint64_t);

  for (unsigned i = 0; i < STRIDED8_ELEMENTS; ++i)
    for (unsigned word = 0; word < STRIDED8_ROW_WORDS; ++word)
      strided8_target[i][word] = 0xdeadbeefcafef00dUL;

  asm volatile(
      "vsetivli zero, 8, e32, m1, tu, mu\n"
      "vle32.v v9,  (%[field0])\n"
      "vle32.v v10, (%[field1])\n"
      "vle32.v v11, (%[field2])\n"
      "vle32.v v12, (%[field3])\n"
      "vle32.v v13, (%[field4])\n"
      "vle32.v v14, (%[field5])\n"
      "vle32.v v15, (%[field6])\n"
      "vle32.v v16, (%[field7])\n"
      "vsetivli zero, 4, e32, mf2, tu, mu\n"
      "vssseg8e64.v v9, (%[target]), %[stride]\n"
      :
      : [field0] "r"(strided8_fields[0]),
        [field1] "r"(strided8_fields[1]),
        [field2] "r"(strided8_fields[2]),
        [field3] "r"(strided8_fields[3]),
        [field4] "r"(strided8_fields[4]),
        [field5] "r"(strided8_fields[5]),
        [field6] "r"(strided8_fields[6]),
        [field7] "r"(strided8_fields[7]), [target] "r"(strided8_target),
        [stride] "r"(stride)
      : "memory");
  wait_for_memory();

  for (unsigned i = 0; i < STRIDED8_ELEMENTS; ++i) {
    for (unsigned word = 0; word < STRIDED8_ROW_WORDS; ++word) {
      const uint64_t expected =
          i < 4 && word < STRIDED8_FIELDS
              ? strided8_fields[word][i]
              : 0xdeadbeefcafef00dUL;
      check_dword("strided segment store nf8 e64 from e32",
                  i * STRIDED8_ROW_WORDS + word,
                  strided8_target[i][word], expected);
    }
  }
}

static void test_strided_segment_store_nf8_e64_mixed_layout(void) {
  const unsigned long stride = STRIDED8_ROW_WORDS * sizeof(uint64_t);

  for (unsigned i = 0; i < STRIDED8_ELEMENTS; ++i)
    for (unsigned word = 0; word < STRIDED8_ROW_WORDS; ++word)
      strided8_target[i][word] = 0xdeadbeefcafef00dUL;

  asm volatile(
      "vsetivli zero, 4, e64, m1, tu, mu\n"
      "vle64.v v9,  (%[field0])\n"
      "vle64.v v10, (%[field1])\n"
      "vsetivli zero, 8, e32, m1, tu, mu\n"
      "vle32.v v11, (%[field2])\n"
      "vle32.v v12, (%[field3])\n"
      "vle32.v v13, (%[field4])\n"
      "vle32.v v14, (%[field5])\n"
      "vle32.v v15, (%[field6])\n"
      "vle32.v v16, (%[field7])\n"
      "vsetivli zero, 4, e32, mf2, tu, mu\n"
      "vssseg8e64.v v9, (%[target]), %[stride]\n"
      :
      : [field0] "r"(strided8_fields[0]),
        [field1] "r"(strided8_fields[1]),
        [field2] "r"(strided8_fields[2]),
        [field3] "r"(strided8_fields[3]),
        [field4] "r"(strided8_fields[4]),
        [field5] "r"(strided8_fields[5]),
        [field6] "r"(strided8_fields[6]),
        [field7] "r"(strided8_fields[7]), [target] "r"(strided8_target),
        [stride] "r"(stride)
      : "memory");
  wait_for_memory();

  for (unsigned i = 0; i < STRIDED8_ELEMENTS; ++i) {
    for (unsigned word = 0; word < STRIDED8_ROW_WORDS; ++word) {
      const uint64_t expected =
          i < 4 && word < STRIDED8_FIELDS
              ? strided8_fields[word][i]
              : 0xdeadbeefcafef00dUL;
      check_dword("strided segment store nf8 e64 mixed layout",
                  i * STRIDED8_ROW_WORDS + word,
                  strided8_target[i][word], expected);
    }
  }
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  initialize_data();
  test_unit_segment_load_m4();
  test_unit_segment_load_vstart_m4();
  test_masked_segment_load_preserves_mixed_layout();
  test_indexed_segment_load_m4();
  test_indexed_segment_load_e16_m4_page_boundary();
  test_indexed_segment_v8_decode();
  test_masked_indexed_segment_store_m4();
  test_masked_indexed_segment_store_vstart_m4();
  test_strided_segment_store_m4();
  test_strided_segment_store_mixed_layout_e8_vstart();
  test_masked_strided_segment_load_nf5_e64();
  test_strided_segment_store_nf8_e64();
  test_strided_segment_store_nf8_e64_mf2();
  test_strided_segment_store_nf8_e64_from_e32_layout();
  test_strided_segment_store_nf8_e64_mixed_layout();
  EXIT_CHECK();
}
