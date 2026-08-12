// Directed restart tests for indexed memory operations whose index EEW differs
// from the data SEW and whose first active element is inside an aggregate word.

#include "vector_macros.h"

#define ELEMENTS 79
#define VSTART 63
#define SENTINEL 0xdeadU
#define BYTE_INDEX_ELEMENTS 12
#define BYTE_INDEX_VSTART 7
#define SENTINEL32 0xdeadbeefU
#define MIXED_INDEX_ELEMENTS 24
#define UNIFORM_INDEX_VSTART 17
#define E64_RESTART_ELEMENTS 93
#define E64_RESTART_VSTART 68
#define OVERLAP_LOAD_ELEMENTS 59

static uint16_t source[ELEMENTS] __attribute__((aligned(128)));
static uint32_t indices[ELEMENTS] __attribute__((aligned(128)));
static uint16_t loaded[ELEMENTS] __attribute__((aligned(128)));
static uint16_t stored[ELEMENTS] __attribute__((aligned(128)));
static uint16_t initial[ELEMENTS] __attribute__((aligned(128)));
static uint32_t source32[1] __attribute__((aligned(128)));
static uint8_t indices8[BYTE_INDEX_ELEMENTS] __attribute__((aligned(128)));
static uint32_t initial32[BYTE_INDEX_ELEMENTS] __attribute__((aligned(128)));
static uint32_t loaded32[BYTE_INDEX_ELEMENTS] __attribute__((aligned(128)));
static uint64_t overlap_group[128] __attribute__((aligned(128)));
static uint32_t overlap_store_target[16] __attribute__((aligned(128)));
static uint64_t mixed_indices64_first[16] __attribute__((aligned(128)));
static uint32_t mixed_indices32_second[16] __attribute__((aligned(128)));
static uint32_t mixed_source[MIXED_INDEX_ELEMENTS] __attribute__((aligned(128)));
static uint32_t mixed_loaded[MIXED_INDEX_ELEMENTS] __attribute__((aligned(128)));
static uint32_t uniform_index_words[2 * MIXED_INDEX_ELEMENTS]
    __attribute__((aligned(128)));
static uint32_t uniform_source[MIXED_INDEX_ELEMENTS] __attribute__((aligned(128)));
static uint32_t uniform_initial[MIXED_INDEX_ELEMENTS] __attribute__((aligned(128)));
static uint32_t uniform_loaded[MIXED_INDEX_ELEMENTS] __attribute__((aligned(128)));
static uint64_t e64_restart_source[E64_RESTART_ELEMENTS] __attribute__((aligned(128)));
static uint64_t e64_restart_indices[E64_RESTART_ELEMENTS] __attribute__((aligned(128)));
static uint64_t e64_restart_initial[E64_RESTART_ELEMENTS] __attribute__((aligned(128)));
static uint64_t e64_restart_loaded[E64_RESTART_ELEMENTS] __attribute__((aligned(128)));
static uint16_t overlap_load_source[OVERLAP_LOAD_ELEMENTS] __attribute__((aligned(128)));
static uint32_t overlap_load_indices[128] __attribute__((aligned(128)));
static uint16_t overlap_load_result[OVERLAP_LOAD_ELEMENTS] __attribute__((aligned(128)));

static void initialize_data(void) {
  for (unsigned i = 0; i < ELEMENTS; ++i) {
    source[i] = 0x1000U + i;
    indices[i] = i * sizeof(source[0]);
    loaded[i] = 0;
    stored[i] = SENTINEL;
    initial[i] = SENTINEL;
  }
  source32[0] = 0xfcfdfeffU;
  for (unsigned i = 0; i < BYTE_INDEX_ELEMENTS; ++i) {
    indices8[i] = 0;
    initial32[i] = SENTINEL32;
    loaded32[i] = 0;
  }
  for (unsigned i = 0; i < 128; ++i)
    overlap_group[i] = 0;
  for (unsigned i = 0; i < 16; ++i)
    overlap_store_target[i] = SENTINEL32;

  for (unsigned i = 0; i < MIXED_INDEX_ELEMENTS; ++i) {
    mixed_source[i] = 0x30000000U + i;
    mixed_loaded[i] = 0;
    uniform_index_words[2 * i] = i * sizeof(uniform_source[0]);
    uniform_index_words[2 * i + 1] = 0;
    uniform_source[i] = 0x40000000U + i;
    uniform_initial[i] = SENTINEL32;
    uniform_loaded[i] = 0;
  }
  for (unsigned i = 0; i < E64_RESTART_ELEMENTS; ++i) {
    e64_restart_source[i] = 0x1234000000000000ULL + i;
    e64_restart_indices[i] = i * sizeof(e64_restart_source[0]);
    e64_restart_initial[i] = 0xdeadbeef00000000ULL + i;
    e64_restart_loaded[i] = 0;
  }
  for (unsigned i = 0; i < 128; ++i)
    overlap_load_indices[i] =
        (i % OVERLAP_LOAD_ELEMENTS) * sizeof(overlap_load_source[0]);
  for (unsigned i = 0; i < OVERLAP_LOAD_ELEMENTS; ++i) {
    overlap_load_source[i] = 0x5000U + i;
    overlap_load_result[i] = 0;
  }
  for (unsigned i = 0; i < 16; ++i) {
    mixed_indices64_first[i] = i * sizeof(mixed_source[0]);
    // v17 is written as e32 but is later consumed as eight e64 offsets.
    mixed_indices32_second[2 * (i & 7)] =
        (16 + (i & 7)) * sizeof(mixed_source[0]);
    mixed_indices32_second[2 * (i & 7) + 1] = 0;
  }

  // e32 element 11 remains zero; e64 element 11 is its byte index.
  overlap_group[11] = 4 * sizeof(overlap_store_target[0]);
}

static void wait_for_memory(void) {
  unsigned long vl;
  asm volatile("csrr %0, vl\n fence rw, rw" : "=r"(vl) :: "memory");
}

static void check_word(const char *name, unsigned index, uint16_t observed,
                       uint16_t expected) {
  if (observed == expected)
    return;
  printf("%s failed at %d: got=%x expected=%x\n", name, index, observed,
         expected);
  ++num_failed;
}

static void test_indexed_load_vstart(void) {
  asm volatile(
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vle16.v v12, (%[initial])\n"
      "vle32.v v24, (%[indices])\n"
      "csrw vstart, %[vstart]\n"
      "vluxei32.v v12, (%[source]), v24\n"
      "vse16.v v12, (%[loaded])\n"
      :
      : [vl] "r"(ELEMENTS), [vstart] "r"(VSTART),
        [initial] "r"(initial), [indices] "r"(indices),
        [source] "r"(source), [loaded] "r"(loaded)
      : "memory");
  wait_for_memory();

  for (unsigned i = 0; i < ELEMENTS; ++i)
    check_word("indexed load vstart", i, loaded[i],
               i < VSTART ? SENTINEL : source[i]);
}

static void test_indexed_store_vstart(void) {
  asm volatile(
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vle16.v v8, (%[source])\n"
      "vle32.v v24, (%[indices])\n"
      "csrw vstart, %[vstart]\n"
      "vsuxei32.v v8, (%[stored]), v24\n"
      :
      : [vl] "r"(ELEMENTS), [vstart] "r"(VSTART), [source] "r"(source),
        [indices] "r"(indices), [stored] "r"(stored)
      : "memory");
  wait_for_memory();

  for (unsigned i = 0; i < ELEMENTS; ++i)
    check_word("indexed store vstart", i, stored[i],
               i < VSTART ? SENTINEL : source[i]);
}

static void test_byte_indexed_load_vstart(void) {
  asm volatile(
      "vsetvli zero, %[vl], e32, m4, tu, mu\n"
      "vle32.v v8, (%[initial])\n"
      "vle8.v v1, (%[indices])\n"
      "csrw vstart, %[vstart]\n"
      "vluxei8.v v8, (%[source]), v1\n"
      "vse32.v v8, (%[loaded])\n"
      :
      : [vl] "r"(BYTE_INDEX_ELEMENTS), [vstart] "r"(BYTE_INDEX_VSTART),
        [initial] "r"(initial32), [indices] "r"(indices8),
        [source] "r"(source32), [loaded] "r"(loaded32)
      : "memory");
  wait_for_memory();

  for (unsigned i = 0; i < BYTE_INDEX_ELEMENTS; ++i) {
    uint32_t expected = i < BYTE_INDEX_VSTART ? SENTINEL32 : source32[0];
    if (loaded32[i] == expected)
      continue;
    printf("byte-indexed load vstart failed at %d: got=%x expected=%x\n", i,
           loaded32[i], expected);
    ++num_failed;
  }
}

static void test_overlapping_indexed_store_vstart(void) {
  asm volatile(
      "vl8re64.v v16, (%[group])\n"
      "vsetvli zero, %[vl], e32, m4, tu, mu\n"
      "csrw vstart, %[vstart]\n"
      "vsoxei64.v v16, (%[target]), v16\n"
      :
      : [group] "r"(overlap_group), [vl] "r"(BYTE_INDEX_ELEMENTS),
        [vstart] "r"(BYTE_INDEX_ELEMENTS - 1),
        [target] "r"(overlap_store_target)
      : "memory");
  wait_for_memory();

  for (unsigned i = 0; i < 16; ++i) {
    uint32_t expected = i == 4 ? 0 : SENTINEL32;
    if (overlap_store_target[i] == expected)
      continue;
    printf("overlapping indexed store vstart failed at %d: got=%x expected=%x\n",
           i, overlap_store_target[i], expected);
    ++num_failed;
  }
}

static void test_mixed_layout_index_group(void) {
  asm volatile(
      "vsetvli zero, %[vl16], e64, m1, ta, ma\n"
      "vle64.v v16, (%[first])\n"
      "vsetvli zero, %[vl16], e32, m1, ta, ma\n"
      "vle32.v v17, (%[second])\n"
      "vsetvli zero, %[vl24], e32, m4, ta, ma\n"
      "vluxei64.v v0, (%[source]), v16\n"
      "vse32.v v0, (%[loaded])\n"
      :
      : [vl16] "r"(16), [vl24] "r"(MIXED_INDEX_ELEMENTS),
        [first] "r"(mixed_indices64_first),
        [second] "r"(mixed_indices32_second), [source] "r"(mixed_source),
        [loaded] "r"(mixed_loaded)
      : "memory");
  wait_for_memory();

  for (unsigned i = 0; i < MIXED_INDEX_ELEMENTS; ++i) {
    if (mixed_loaded[i] == mixed_source[i])
      continue;
    printf("mixed-layout indexed load failed at %d: got=%x expected=%x\n", i,
           mixed_loaded[i], mixed_source[i]);
    ++num_failed;
  }
}

static void test_uniform_old_layout_cross_register_vstart(void) {
  asm volatile(
      "vsetvli zero, %[index_vl], e32, m2, ta, ma\n"
      "vle32.v v16, (%[indices])\n"
      "vsetvli zero, %[data_vl], e32, m4, tu, mu\n"
      "vle32.v v0, (%[initial])\n"
      "csrw vstart, %[vstart]\n"
      "vluxei64.v v0, (%[source]), v16\n"
      "vse32.v v0, (%[loaded])\n"
      :
      : [index_vl] "r"(2 * MIXED_INDEX_ELEMENTS),
        [data_vl] "r"(MIXED_INDEX_ELEMENTS),
        [vstart] "r"(UNIFORM_INDEX_VSTART), [indices] "r"(uniform_index_words),
        [initial] "r"(uniform_initial), [source] "r"(uniform_source),
        [loaded] "r"(uniform_loaded)
      : "memory");
  wait_for_memory();

  for (unsigned i = 0; i < MIXED_INDEX_ELEMENTS; ++i) {
    uint32_t expected = i < UNIFORM_INDEX_VSTART ? SENTINEL32 : uniform_source[i];
    if (uniform_loaded[i] == expected)
      continue;
    printf("uniform-layout indexed load failed at %d: got=%x expected=%x\n", i,
           uniform_loaded[i], expected);
    ++num_failed;
  }
}

static void test_e64_m8_cross_register_vstart(void) {
  asm volatile(
      "vsetvli zero, %[vl], e64, m8, tu, mu\n"
      "vle64.v v16, (%[initial])\n"
      "vle64.v v0, (%[indices])\n"
      "csrw vstart, %[vstart]\n"
      "vluxei64.v v16, (%[source]), v0\n"
      "vse64.v v16, (%[loaded])\n"
      :
      : [vl] "r"(E64_RESTART_ELEMENTS), [vstart] "r"(E64_RESTART_VSTART),
        [initial] "r"(e64_restart_initial), [indices] "r"(e64_restart_indices),
        [source] "r"(e64_restart_source), [loaded] "r"(e64_restart_loaded)
      : "memory");
  wait_for_memory();

  for (unsigned i = 0; i < E64_RESTART_ELEMENTS; ++i) {
    uint64_t expected = i < E64_RESTART_VSTART
                            ? e64_restart_initial[i]
                            : e64_restart_source[i];
    if (e64_restart_loaded[i] == expected)
      continue;
    printf("e64 m8 indexed load vstart failed at %d: got=%lx expected=%lx\n",
           i, e64_restart_loaded[i], expected);
    ++num_failed;
  }
}

static void test_overlapping_indexed_load(void) {
  asm volatile(
      "vsetvli zero, %[index_vl], e32, m4, tu, mu\n"
      "vle32.v v28, (%[indices])\n"
      "vsetvli zero, %[vl], e16, m2, tu, mu\n"
      "vloxei32.v v28, (%[source]), v28\n"
      "vse16.v v28, (%[loaded])\n"
      :
      : [index_vl] "r"(128), [vl] "r"(OVERLAP_LOAD_ELEMENTS),
        [indices] "r"(overlap_load_indices),
        [source] "r"(overlap_load_source), [loaded] "r"(overlap_load_result)
      : "memory");
  wait_for_memory();

  for (unsigned i = 0; i < OVERLAP_LOAD_ELEMENTS; ++i) {
    unsigned index = overlap_load_indices[i] / sizeof(overlap_load_source[0]);
    if (overlap_load_result[i] == overlap_load_source[index])
      continue;
    printf("overlapping indexed load failed at %d: got=%x expected=%x\n", i,
           overlap_load_result[i], overlap_load_source[index]);
    ++num_failed;
  }
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  initialize_data();
  test_indexed_load_vstart();
  test_indexed_store_vstart();
  test_byte_indexed_load_vstart();
  test_overlapping_indexed_store_vstart();
  test_mixed_layout_index_group();
  test_uniform_old_layout_cross_register_vstart();
  test_e64_m8_cross_register_vstart();
  test_overlapping_indexed_load();
  EXIT_CHECK();
}
