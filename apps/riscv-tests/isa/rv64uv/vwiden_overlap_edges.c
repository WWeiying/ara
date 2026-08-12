// Legal widening source/destination overlap regressions.

#include "vector_macros.h"

#define VLMAX 256

static int32_t wide_source[VLMAX] __attribute__((aligned(128)));
static int16_t narrow_source[VLMAX] __attribute__((aligned(128)));
static int32_t destination_seed[VLMAX] __attribute__((aligned(128)));
static int32_t result[VLMAX] __attribute__((aligned(128)));
static uint8_t zero_vl_before[8 * 128] __attribute__((aligned(128)));
static uint8_t zero_vl_after[8 * 128] __attribute__((aligned(128)));
static uint8_t dual_overlap_seed[8 * 128] __attribute__((aligned(128)));
static uint32_t dual_overlap_narrow[128] __attribute__((aligned(128)));
static uint64_t dual_overlap_result[128] __attribute__((aligned(128)));

static void initialize_data(void) {
  for (unsigned index = 0; index < VLMAX; ++index) {
    wide_source[index] = (int32_t)(0x102030 + 97 * index);
    narrow_source[index] = (int16_t)(-3000 + 37 * index);
    destination_seed[index] = (int32_t)(0x51000000u + 131u * index);
    result[index] = 0;
  }
  for (unsigned byte = 0; byte < sizeof(dual_overlap_seed); ++byte)
    dual_overlap_seed[byte] = (uint8_t)(0x35u + 29u * byte);
  for (unsigned index = 0; index < 128; ++index) {
    dual_overlap_narrow[index] = UINT32_C(0x10203040) + 0x010307u * index;
    dual_overlap_result[index] = 0;
  }
}

static uint64_t load_le64(const uint8_t *bytes) {
  uint64_t value = 0;
  for (unsigned byte = 0; byte < 8; ++byte)
    value |= (uint64_t)bytes[byte] << (8 * byte);
  return value;
}

static uint32_t load_le32(const uint8_t *bytes) {
  uint32_t value = 0;
  for (unsigned byte = 0; byte < 4; ++byte)
    value |= (uint32_t)bytes[byte] << (8 * byte);
  return value;
}

static int32_t overlapped_tail_value(unsigned destination_index, unsigned vl) {
  if (destination_index < VLMAX / 2)
    return destination_seed[destination_index];

  unsigned source_index = 2 * (destination_index - VLMAX / 2);
  uint32_t old_value = (uint32_t)destination_seed[destination_index];
  uint32_t low = source_index < vl
                     ? (uint16_t)narrow_source[source_index]
                     : old_value & UINT32_C(0xffff);
  uint32_t high = source_index + 1 < vl
                      ? (uint16_t)narrow_source[source_index + 1]
                      : old_value >> 16;
  return (int32_t)(low | (high << 16));
}

static void test_vwadd_wv_high_overlap(unsigned vl) {
  // For a widening operation, an e16,m4 source may legally overlap the
  // high-numbered half of its e32,m8 destination. v12-v15 is therefore a
  // legal narrow source for destination v8-v15.
  asm volatile(
      "vsetvli zero, %[vlmax], e32, m8, tu, mu\n"
      "vle32.v v8, (%[seed])\n"
      "vsetvli zero, %[vl], e32, m8, tu, mu\n"
      "vle32.v v24, (%[wide])\n"
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vle16.v v12, (%[narrow])\n"
      "vwadd.wv v8, v24, v12\n"
      "vsetvli zero, %[vlmax], e32, m8, tu, mu\n"
      "vse32.v v8, (%[result])\n"
      :
      : [vl] "r"(vl), [vlmax] "r"(VLMAX), [seed] "r"(destination_seed),
        [wide] "r"(wide_source), [narrow] "r"(narrow_source),
        [result] "r"(result)
      : "memory");

  MEMORY_BARRIER;
  unsigned mismatch_count = 0;
  for (unsigned index = 0; index < VLMAX; ++index) {
    int32_t expected = index < vl
                           ? wide_source[index] + (int32_t)narrow_source[index]
                           : overlapped_tail_value(index, vl);
    if (result[index] != expected) {
      if (mismatch_count < 8)
        printf("vwadd.wv high-overlap vl=%d failed at %d: got=%x expected=%x\n",
               vl, index, (uint32_t)result[index], (uint32_t)expected);
      ++mismatch_count;
    }
  }
  if (mismatch_count != 0) {
    printf("vwadd.wv high-overlap vl=%d mismatch count=%d\n", vl, mismatch_count);
    ++num_failed;
  }
}

static void test_vwmaccu_vx_high_overlap(unsigned vl) {
  const uint32_t scalar = 7;

  // vwmaccu also reads the wide destination as its accumulator.  With this
  // short VL, the active wide destination registers end below the active
  // narrow source registers even though their architectural groups overlap.
  asm volatile(
      "vsetvli zero, %[vlmax], e32, m8, tu, mu\n"
      "vle32.v v8, (%[seed])\n"
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vle16.v v12, (%[narrow])\n"
      "vwmaccu.vx v8, %[scalar], v12\n"
      "vsetvli zero, %[vlmax], e32, m8, tu, mu\n"
      "vse32.v v8, (%[result])\n"
      :
      : [vl] "r"(vl), [vlmax] "r"(VLMAX), [scalar] "r"(scalar),
        [seed] "r"(destination_seed), [narrow] "r"(narrow_source),
        [result] "r"(result)
      : "memory");

  MEMORY_BARRIER;
  unsigned mismatch_count = 0;
  for (unsigned index = 0; index < VLMAX; ++index) {
    uint32_t expected = index < vl
                            ? (uint32_t)destination_seed[index] +
                                  scalar * (uint16_t)narrow_source[index]
                            : (uint32_t)overlapped_tail_value(index, vl);
    if ((uint32_t)result[index] != expected) {
      if (mismatch_count < 8)
        printf("vwmaccu.vx high-overlap vl=%d failed at %d: got=%x expected=%x\n",
               vl, index, (uint32_t)result[index], expected);
      ++mismatch_count;
    }
  }
  if (mismatch_count != 0) {
    printf("vwmaccu.vx high-overlap vl=%d mismatch count=%d\n", vl,
           mismatch_count);
    ++num_failed;
  }
}

static void test_vwmaccu_vx_zero_vl_overlap(void) {
  const unsigned source_vl = 79;
  const unsigned zero_vl = 0;
  const uint32_t scalar = 7;

  // Establish the legal e16,m4 high source overlap in v12-v15, then issue the
  // widening accumulator with VL=0.  No active element exists, so the request
  // must bypass overlap preparation, leave v8-v15 unchanged, and allow the
  // following whole-register store to make forward progress.
  asm volatile(
      "vsetvli zero, %[vlmax], e32, m8, tu, mu\n"
      "vle32.v v8, (%[seed])\n"
      "vsetvli zero, %[source_vl], e16, m4, tu, mu\n"
      "vle16.v v12, (%[narrow])\n"
      "vs8r.v v8, (%[before])\n"
      "vsetvli zero, %[zero_vl], e16, m4, tu, mu\n"
      "vwmaccu.vx v8, %[scalar], v12\n"
      "vs8r.v v8, (%[after])\n"
      "fence rw, rw\n"
      :
      : [vlmax] "r"(VLMAX), [source_vl] "r"(source_vl),
        [zero_vl] "r"(zero_vl), [scalar] "r"(scalar),
        [seed] "r"(destination_seed), [narrow] "r"(narrow_source),
        [before] "r"(zero_vl_before), [after] "r"(zero_vl_after)
      : "memory");

  MEMORY_BARRIER;
  for (unsigned byte = 0; byte < sizeof(zero_vl_before); ++byte) {
    if (zero_vl_after[byte] != zero_vl_before[byte]) {
      printf("vwmaccu.vx zero-vl overlap failed at byte %d: "
             "got=%x expected=%x\n",
             byte, zero_vl_after[byte], zero_vl_before[byte]);
      ++num_failed;
      return;
    }
  }
}

static void test_vwaddu_wv_dual_overlap(void) {
  const unsigned byte_vl = sizeof(dual_overlap_seed);
  const unsigned operation_vl = 103;
  const unsigned wide_vl = 128;

  // Reproduce the legal seed-6 shape exactly. The destination is also the
  // wide source (v0-v7), while the narrow source v4-v7 aliases its high half.
  // Both source views must survive layout normalization until the operation
  // has consumed them.
  asm volatile(
      "vsetvli zero, %[byte_vl], e8, m8, tu, mu\n"
      "vle8.v v0, (%[seed])\n"
      "vsetvli zero, %[operation_vl], e32, m4, tu, mu\n"
      "vle32.v v4, (%[narrow])\n"
      "vwaddu.wv v0, v0, v4\n"
      "vsetvli zero, %[wide_vl], e64, m8, tu, mu\n"
      "vse64.v v0, (%[result])\n"
      "fence rw, rw\n"
      :
      : [byte_vl] "r"(byte_vl), [operation_vl] "r"(operation_vl),
        [wide_vl] "r"(wide_vl), [seed] "r"(dual_overlap_seed),
        [narrow] "r"(dual_overlap_narrow), [result] "r"(dual_overlap_result)
      : "memory");

  MEMORY_BARRIER;
  unsigned mismatch_count = 0;
  for (unsigned index = 0; index < wide_vl; ++index) {
    uint8_t wide_bytes[8];
    for (unsigned byte = 0; byte < 8; ++byte) {
      unsigned raw_offset = 8 * index + byte;
      if (raw_offset >= 4 * 128 &&
          raw_offset < 4 * 128 + operation_vl * sizeof(uint32_t)) {
        unsigned narrow_offset = raw_offset - 4 * 128;
        unsigned narrow_index = narrow_offset / sizeof(uint32_t);
        unsigned narrow_byte = narrow_offset % sizeof(uint32_t);
        wide_bytes[byte] =
            (uint8_t)(dual_overlap_narrow[narrow_index] >> (8 * narrow_byte));
      } else {
        wide_bytes[byte] = dual_overlap_seed[raw_offset];
      }
    }
    uint64_t wide_source_value = load_le64(wide_bytes);
    uint64_t expected = index < operation_vl
                            ? wide_source_value + dual_overlap_narrow[index]
                            : wide_source_value;
    if (dual_overlap_result[index] != expected) {
      if (mismatch_count < 8)
        printf("vwaddu.wv dual-overlap failed at %d: got=%lx expected=%lx\n",
               index, dual_overlap_result[index], expected);
      ++mismatch_count;
    }
  }
  if (mismatch_count != 0) {
    printf("vwaddu.wv dual-overlap mismatch count=%d\n", mismatch_count);
    ++num_failed;
  }
}

static void test_vwaddu_wv_dual_overlap_wide_ready(void) {
  const unsigned operation_vl = 103;
  const unsigned wide_vl = 128;

  // Complement the previous case by making the e64,m8 wide source the
  // physical view that is initially ready. The implementation must snapshot
  // that wide source, expose the overlapping e32,m4 narrow view, and repair
  // the destination only after the original instruction has consumed both.
  asm volatile(
      "vsetvli zero, %[wide_vl], e64, m8, tu, mu\n"
      "vle64.v v0, (%[seed])\n"
      "vsetvli zero, %[operation_vl], e32, m4, tu, mu\n"
      "vwaddu.wv v0, v0, v4\n"
      "vsetvli zero, %[wide_vl], e64, m8, tu, mu\n"
      "vse64.v v0, (%[result])\n"
      "fence rw, rw\n"
      :
      : [operation_vl] "r"(operation_vl), [wide_vl] "r"(wide_vl),
        [seed] "r"(dual_overlap_seed), [result] "r"(dual_overlap_result)
      : "memory");

  MEMORY_BARRIER;
  unsigned mismatch_count = 0;
  for (unsigned index = 0; index < wide_vl; ++index) {
    uint64_t wide_source_value = load_le64(&dual_overlap_seed[8 * index]);
    uint32_t narrow_source_value =
        load_le32(&dual_overlap_seed[4 * 128 + 4 * index]);
    uint64_t expected = index < operation_vl
                            ? wide_source_value + narrow_source_value
                            : wide_source_value;
    if (dual_overlap_result[index] != expected) {
      if (mismatch_count < 8)
        printf("vwaddu.wv wide-ready overlap failed at %d: "
               "got=%lx expected=%lx\n",
               index, dual_overlap_result[index], expected);
      ++mismatch_count;
    }
  }
  if (mismatch_count != 0) {
    printf("vwaddu.wv wide-ready overlap mismatch count=%d\n", mismatch_count);
    ++num_failed;
  }
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  initialize_data();
  test_vwadd_wv_high_overlap(79);
  test_vwadd_wv_high_overlap(150);
  test_vwadd_wv_high_overlap(200);
  test_vwadd_wv_high_overlap(255);
  test_vwmaccu_vx_high_overlap(79);
  test_vwmaccu_vx_zero_vl_overlap();
  test_vwaddu_wv_dual_overlap();
  test_vwaddu_wv_dual_overlap_wide_ready();
  EXIT_CHECK();
}
