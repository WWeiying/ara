// VRGATHER regressions for scalar indices outside VLMAX.

#include "vector_macros.h"

#define VL 79

static uint16_t source[VL] __attribute__((aligned(128)));
static uint16_t old_destination[VL] __attribute__((aligned(128)));
static uint16_t indices[VL] __attribute__((aligned(128)));
static uint16_t vector_result[VL] __attribute__((aligned(128)));
static uint8_t whole_register[128] __attribute__((aligned(128)));

#define DUAL_LAYOUT_VL 9
static uint8_t dual_layout_raw[2 * 128] __attribute__((aligned(128)));
static uint64_t dual_layout_result[DUAL_LAYOUT_VL]
    __attribute__((aligned(128)));

#define LIFETIME_VL 85
static uint32_t lifetime_source[LIFETIME_VL] __attribute__((aligned(128)));
static uint32_t lifetime_result[LIFETIME_VL] __attribute__((aligned(128)));
static uint8_t zero_vl_source[128] __attribute__((aligned(128)));

static uint16_t load_u16_le(const uint8_t *bytes) {
  return (uint16_t)bytes[0] | ((uint16_t)bytes[1] << 8);
}

static uint64_t load_u64_le(const uint8_t *bytes) {
  uint64_t value = 0;
  for (unsigned byte = 0; byte < sizeof(value); ++byte)
    value |= (uint64_t)bytes[byte] << (8 * byte);
  return value;
}

static void test_scalar_out_of_range(void) {
  for (unsigned index = 0; index < VL; ++index) {
    source[index] = (uint16_t)(0x2100u + 23u * index);
    old_destination[index] = (uint16_t)(0xb100u + 17u * index);
  }

  // The large scalar has nonzero bits above bit 15. No source operand is
  // architecturally read; every active destination element must become zero.
  unsigned long scalar = 0x80021c78UL;
  asm volatile(
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vle16.v v20, (%[source])\n"
      "vle16.v v0, (%[old])\n"
      "vrgather.vx v0, v20, %[scalar]\n"
      // Match strict-checkpoint consumption: immediately read the first
      // destination register with a whole-register store.
      "vs1r.v v0, (%[result])\n"
      "csrr zero, vl\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(VL), [source] "r"(source), [old] "r"(old_destination),
        [scalar] "r"(scalar), [result] "r"(whole_register)
      : "memory");

  for (unsigned byte = 0; byte < sizeof(whole_register); ++byte) {
    if (whole_register[byte] != 0) {
      printf("vrgather.vx out-of-range failed at byte %d: got=%x expected=0\n",
             byte, whole_register[byte]);
      ++num_failed;
      break;
    }
  }
}

static void test_final_vector_index_out_of_range(void) {
  unsigned long scalar_result;

  for (unsigned index = 0; index < VL; ++index)
    indices[index] = (uint16_t)index;
  indices[VL - 1] = 300;

  asm volatile(
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vle16.v v20, (%[source])\n"
      "vle16.v v24, (%[indices])\n"
      "vrgather.vv v8, v20, v24\n"
      "vmv.x.s %[scalar], v8\n"
      "vse16.v v8, (%[result])\n"
      "fence rw, rw\n"
      : [scalar] "=r"(scalar_result)
      : [vl] "r"(VL), [source] "r"(source), [indices] "r"(indices),
        [result] "r"(vector_result)
      : "memory");

  if ((uint16_t)scalar_result != source[0]) {
    printf("vrgather final-oor scalar handoff failed: got=%x expected=%x\n",
           (unsigned)(uint16_t)scalar_result, source[0]);
    ++num_failed;
    return;
  }

  for (unsigned index = 0; index < VL; ++index) {
    uint16_t expected = index == VL - 1 ? 0 : source[index];
    if (vector_result[index] != expected) {
      printf("vrgather final-oor failed at %d: got=%x expected=%x\n",
             index, vector_result[index], expected);
      ++num_failed;
      return;
    }
  }
}

static void test_scalar_source_lifetime(void) {
  const unsigned long gather_index = 8;
  const uint32_t expected = 0xa5c3085au;

  for (unsigned index = 0; index < LIFETIME_VL; ++index) {
    lifetime_source[index] = 0x41000000u + 37u * index;
    lifetime_result[index] = 0;
  }
  lifetime_source[gather_index] = expected;

  // VRGATHER.vx rereads one vs2 element for every destination element.  A
  // younger writer must not overwrite vs2 after only part of the gather has
  // consumed it.
  asm volatile(
      "vsetvli zero, %[vl], e32, m8, tu, mu\n"
      "vle32.v v0, (%[source])\n"
      "vrgather.vx v16, v0, %[index]\n"
      "vmv.v.i v0, 0\n"
      "vse32.v v16, (%[result])\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(LIFETIME_VL), [source] "r"(lifetime_source),
        [index] "r"(gather_index), [result] "r"(lifetime_result)
      : "memory");

  for (unsigned index = 0; index < LIFETIME_VL; ++index) {
    if (lifetime_result[index] != expected) {
      printf("vrgather.vx source lifetime failed at %d: got=%x expected=%x\n",
             index, lifetime_result[index], expected);
      ++num_failed;
      return;
    }
  }
}

static void test_vrgatherei16_dual_source_layout(void) {
  static const uint16_t index_pattern[DUAL_LAYOUT_VL] = {
      0, 0, 1, 0, 1, 0, 13, 13, 0};

  // v28-v29 is first established as an e8 whole-register image.  The gather
  // then needs v28-v29 as e64,m2 data while overlapping v29 is simultaneously
  // interpreted as an e16,mf2 index source.  Both views therefore require a
  // layout conversion from the same raw register state.
  for (unsigned byte = 0; byte < sizeof(dual_layout_raw); ++byte)
    dual_layout_raw[byte] = (uint8_t)(0x31u + 29u * byte);
  for (unsigned index = 0; index < DUAL_LAYOUT_VL; ++index) {
    unsigned offset = 128 + 2 * index;
    dual_layout_raw[offset] = (uint8_t)index_pattern[index];
    dual_layout_raw[offset + 1] = (uint8_t)(index_pattern[index] >> 8);
    dual_layout_result[index] = 0;
  }

  asm volatile(
      "vl2re8.v v28, (%[raw])\n"
      "vsetvli zero, %[vl], e64, m2, tu, mu\n"
      "vrgatherei16.vv v26, v28, v29\n"
      "vse64.v v26, (%[result])\n"
      "fence rw, rw\n"
      :
      : [raw] "r"(dual_layout_raw), [vl] "r"(DUAL_LAYOUT_VL),
        [result] "r"(dual_layout_result)
      : "memory");

  for (unsigned index = 0; index < DUAL_LAYOUT_VL; ++index) {
    uint16_t source_index = load_u16_le(&dual_layout_raw[128 + 2 * index]);
    uint64_t expected = load_u64_le(&dual_layout_raw[8 * source_index]);
    if (dual_layout_result[index] != expected) {
      printf("vrgatherei16 dual-layout failed at %d: got=%lx expected=%lx "
             "source_index=%d\n",
             index, dual_layout_result[index], expected, source_index);
      ++num_failed;
      return;
    }
  }
}

static void test_zero_vl_dual_layout_noop_handoff(void) {
  unsigned long popcount;
  long scalar;

  for (unsigned byte = 0; byte < sizeof(zero_vl_source); ++byte)
    zero_vl_source[byte] = (uint8_t)(0x11u * (byte + 1));

  // Establish v3 in an e8 physical layout, then make vrgatherei16 a VL=0
  // architectural no-op. The no-op must not inject a zero-length source
  // snapshot into the SLDU. A following scalar handoff still has to convert
  // and read v3 in the current e32 layout.
  asm volatile(
      "vl1re8.v v3, (%[source])\n"
      "vsetivli zero, 0, e32, m1, tu, mu\n"
      "vrgatherei16.vv v17, v30, v30, v0.t\n"
      "vcpop.m %[popcount], v30\n"
      "vmv.x.s %[scalar], v3\n"
      : [popcount] "=r"(popcount), [scalar] "=r"(scalar)
      : [source] "r"(zero_vl_source)
      : "memory");

  uint32_t expected = (uint32_t)zero_vl_source[0] |
                      ((uint32_t)zero_vl_source[1] << 8) |
                      ((uint32_t)zero_vl_source[2] << 16) |
                      ((uint32_t)zero_vl_source[3] << 24);
  if (popcount != 0 || (uint32_t)scalar != expected) {
    printf("zero-VL gather handoff failed: pop=%lx scalar=%lx expected=%x\n",
           popcount, (unsigned long)scalar, expected);
    ++num_failed;
  }
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  test_scalar_out_of_range();
  test_final_vector_index_out_of_range();
  test_scalar_source_lifetime();
  test_vrgatherei16_dual_source_layout();
  test_zero_vl_dual_layout_noop_handoff();
  EXIT_CHECK();
}
