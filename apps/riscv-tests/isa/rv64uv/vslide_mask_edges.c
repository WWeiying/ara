// Masked VSLIDEUP regressions for partial and whole mask-word strides.

#include "vector_macros.h"

#define E16_VL 79
#define E16_STRIDE 20
#define E8_VL 600
#define E8_STRIDE 300
#define E16_M4_VLMAX 256
#define E64_M4_VLMAX 64
#define E64_NP2_VL 7
#define E64_M2_VLMAX 32
#define E64_NP2_UP_VL 29
#define E64_OVERFLOW_VL 6
#define E64_M1_VLMAX 16
#define E8_RESIDUAL_OFFSET 33
#define E8_RESIDUAL_M2_VL 46
#define E8_RESIDUAL_M8_VL 8

static uint16_t source16[E16_VL] __attribute__((aligned(128)));
static uint16_t old16[E16_VL] __attribute__((aligned(128)));
static uint16_t result16[E16_VL] __attribute__((aligned(128)));
static uint8_t mask16[(E16_VL + 7) / 8] __attribute__((aligned(128)));

static uint8_t source8[E8_VL] __attribute__((aligned(128)));
static uint8_t old8[E8_VL] __attribute__((aligned(128)));
static uint8_t result8[E8_VL] __attribute__((aligned(128)));
static uint8_t mask8[(E8_VL + 7) / 8] __attribute__((aligned(128)));

static uint16_t slide_down_source[E16_M4_VLMAX] __attribute__((aligned(128)));
static uint16_t slide_down_old[E16_M4_VLMAX] __attribute__((aligned(128)));
static uint16_t slide_down_result[E16_M4_VLMAX] __attribute__((aligned(128)));
static uint64_t slide1down_source[14] __attribute__((aligned(128)));
static uint8_t slide1down_mask[2] __attribute__((aligned(128)));
static uint8_t slide_boundary_source[30] __attribute__((aligned(128)));
static uint8_t slide_boundary_old[30] __attribute__((aligned(128)));
static uint8_t slide_boundary_result[30] __attribute__((aligned(128)));
static uint8_t slide_boundary_mask[4] __attribute__((aligned(128)));
static uint64_t slide_np2_source[E64_M4_VLMAX] __attribute__((aligned(128)));
static uint64_t slide_np2_result[E64_NP2_VL] __attribute__((aligned(128)));
static uint64_t slide_np2_up_source[E64_M2_VLMAX] __attribute__((aligned(128)));
static uint64_t slide_np2_up_old[E64_M2_VLMAX] __attribute__((aligned(128)));
static uint64_t slide_np2_up_result[E64_NP2_UP_VL] __attribute__((aligned(128)));
static uint32_t slide_pair_source[15] __attribute__((aligned(128)));
static uint32_t slide_pair_old_down[15] __attribute__((aligned(128)));
static uint32_t slide_pair_old_up[15] __attribute__((aligned(128)));
static uint32_t slide_pair_result_down[15] __attribute__((aligned(128)));
static uint32_t slide_pair_result_up[15] __attribute__((aligned(128)));
static uint8_t slide_pair_mask[2] __attribute__((aligned(128)));
static uint64_t slide_overflow_source[E64_M1_VLMAX] __attribute__((aligned(128)));
static uint64_t slide_overflow_old[E64_M1_VLMAX] __attribute__((aligned(128)));
static uint64_t slide_overflow_result[E64_M1_VLMAX] __attribute__((aligned(128)));
static uint8_t slide_residual_m2_result[E8_RESIDUAL_M2_VL]
    __attribute__((aligned(128)));
static uint8_t slide_residual_m8_result[E8_RESIDUAL_M8_VL]
    __attribute__((aligned(128)));

static void wait_for_vector(void) {
  unsigned long vl;
  asm volatile("csrr %0, vl\n fence rw, rw" : "=r"(vl) :: "memory");
}

static unsigned mask_bit(const uint8_t *mask, unsigned index) {
  return (mask[index >> 3] >> (index & 7)) & 1;
}

static void test_e16_m4_partial_word(void) {
  for (unsigned index = 0; index < E16_VL; ++index) {
    source16[index] = (uint16_t)(0x4100u + 17u * index);
    old16[index] = (uint16_t)(0xa100u + 13u * index);
  }
  for (unsigned index = 0; index < sizeof(mask16); ++index)
    mask16[index] = (uint8_t)(0xa5u ^ (37u * index));

  asm volatile(
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vle16.v v20, (%[source])\n"
      "vle16.v v28, (%[old])\n"
      "vlm.v v0, (%[mask])\n"
      "vslideup.vi v28, v20, 20, v0.t\n"
      "vse16.v v28, (%[result])\n"
      :
      : [vl] "r"(E16_VL), [source] "r"(source16), [old] "r"(old16),
        [mask] "r"(mask16), [result] "r"(result16)
      : "memory");
  wait_for_vector();

  for (unsigned index = 0; index < E16_VL; ++index) {
    uint16_t expected = old16[index];
    if (index >= E16_STRIDE && mask_bit(mask16, index))
      expected = source16[index - E16_STRIDE];
    if (result16[index] != expected) {
      printf("masked vslideup.vi e16,m4 failed at %d: got=%x expected=%x mask=%d\n",
             index, result16[index], expected, mask_bit(mask16, index));
      ++num_failed;
      break;
    }
  }
}

static void test_e8_m8_whole_word(void) {
  for (unsigned index = 0; index < E8_VL; ++index) {
    source8[index] = (uint8_t)(0x31u + 29u * index);
    old8[index] = (uint8_t)(0xc7u + 11u * index);
  }
  for (unsigned index = 0; index < sizeof(mask8); ++index)
    mask8[index] = (uint8_t)(0x96u ^ (19u * index));

  unsigned long stride = E8_STRIDE;
  asm volatile(
      "vsetvli zero, %[vl], e8, m8, tu, mu\n"
      "vle8.v v8, (%[source])\n"
      "vle8.v v16, (%[old])\n"
      "vlm.v v0, (%[mask])\n"
      "vslideup.vx v16, v8, %[stride], v0.t\n"
      "vse8.v v16, (%[result])\n"
      :
      : [vl] "r"(E8_VL), [stride] "r"(stride), [source] "r"(source8),
        [old] "r"(old8), [mask] "r"(mask8), [result] "r"(result8)
      : "memory");
  wait_for_vector();

  for (unsigned index = 0; index < E8_VL; ++index) {
    uint8_t expected = old8[index];
    if (index >= E8_STRIDE && mask_bit(mask8, index))
      expected = source8[index - E8_STRIDE];
    if (result8[index] != expected) {
      printf("masked vslideup.vx e8,m8 failed at %d: got=%x expected=%x mask=%d\n",
             index, result8[index], expected, mask_bit(mask8, index));
      ++num_failed;
      break;
    }
  }
}

static void test_slidedown_partial_tail_undisturbed(void) {
  for (unsigned index = 0; index < E16_M4_VLMAX; ++index) {
    slide_down_source[index] = (uint16_t)(0x2100u + index);
    slide_down_old[index] = (uint16_t)(0x4f00u + index);
  }

  unsigned long active_vl = E16_VL;
  unsigned long full_vl = E16_M4_VLMAX;
  unsigned long out_of_range_offset = ~0UL - 13UL;
  asm volatile(
      "vsetvli zero, %[full_vl], e16, m4, tu, mu\n"
      "vle16.v v4, (%[old])\n"
      "vle16.v v8, (%[source])\n"
      "vsetvli zero, %[active_vl], e16, m4, tu, mu\n"
      "vslidedown.vx v4, v8, %[offset]\n"
      "vsetvli zero, %[full_vl], e16, m4, tu, mu\n"
      "vse16.v v4, (%[result])\n"
      :
      : [full_vl] "r"(full_vl), [active_vl] "r"(active_vl),
        [offset] "r"(out_of_range_offset), [source] "r"(slide_down_source),
        [old] "r"(slide_down_old), [result] "r"(slide_down_result)
      : "memory");
  wait_for_vector();

  for (unsigned index = 0; index < E16_M4_VLMAX; ++index) {
    uint16_t expected = index < E16_VL ? 0 : slide_down_old[index];
    if (slide_down_result[index] != expected) {
      printf("vslidedown tail-undisturbed failed at %d: got=%x expected=%x\n",
             index, slide_down_result[index], expected);
      ++num_failed;
      break;
    }
  }
}

static void test_slide1down_dependent_read(void) {
  for (unsigned index = 0; index < 14; ++index)
    slide1down_source[index] = 0x100u + index;
  slide1down_mask[0] = 0;
  slide1down_mask[1] = 0;

  unsigned long scalar = 1;
  asm volatile(
      "vsetivli zero, 14, e64, m2, tu, mu\n"
      "vle64.v v26, (%[source])\n"
      "vslide1down.vx v14, v26, %[scalar]\n"
      // The compare must observe the scalar tail written by the immediately
      // preceding slide, not a stale value released by an earlier result beat.
      "vmsleu.vx v7, v14, %[scalar]\n"
      "vsm.v v7, (%[mask])\n"
      :
      : [source] "r"(slide1down_source), [scalar] "r"(scalar),
        [mask] "r"(slide1down_mask)
      : "memory");
  wait_for_vector();

  // Only bits 0-13 are active. Bits 14-15 retain the prior v7 tail under tu
  // and therefore are not constrained by this test.
  if (slide1down_mask[0] != 0 || (slide1down_mask[1] & 0x3f) != 0x20) {
    printf("vslide1down dependent read failed: got=%x:%x expected=2x:0\n",
           slide1down_mask[1], slide1down_mask[0]);
    ++num_failed;
  }
}

static void test_slide_result_queue_boundary(void) {
  for (unsigned index = 0; index < 30; ++index) {
    slide_boundary_source[index] = (uint8_t)(0x21u + index);
    slide_boundary_old[index] = (uint8_t)(0xa1u + index);
  }
  for (unsigned index = 0; index < sizeof(slide_boundary_mask); ++index)
    slide_boundary_mask[index] = 0;

  unsigned long scalar = 1;
  asm volatile(
      "vsetivli zero, 30, e8, m4, tu, mu\n"
      "vle8.v v12, (%[source])\n"
      "vle8.v v20, (%[old])\n"
      "vle8.v v28, (%[old])\n"
      "vlm.v v0, (%[mask])\n"
      // The all-zero mask still creates a one-byte logical scalar-tail entry.
      "vslide1down.vx v20, v12, %[scalar], v0.t\n"
      // Stride 23 selects the NP2 path while the older scalar-tail entry is
      // waiting for its final VRF grant.
      "vslideup.vi v28, v12, 23\n"
      "vse8.v v28, (%[result])\n"
      :
      : [source] "r"(slide_boundary_source), [old] "r"(slide_boundary_old),
        [mask] "r"(slide_boundary_mask), [scalar] "r"(scalar),
        [result] "r"(slide_boundary_result)
      : "memory");
  wait_for_vector();

  for (unsigned index = 0; index < 30; ++index) {
    uint8_t expected = index < 23 ? slide_boundary_old[index]
                                  : slide_boundary_source[index - 23];
    if (slide_boundary_result[index] != expected) {
      printf("back-to-back slide boundary failed at %d: got=%x expected=%x\n",
             index, slide_boundary_result[index], expected);
      ++num_failed;
      break;
    }
  }
}

static void test_slidedown_np2_atomic_feedback(void) {
  for (unsigned index = 0; index < E64_M4_VLMAX; ++index)
    slide_np2_source[index] = 0x5100000000000000ull + 0x101ull * index;

  unsigned long full_vl = E64_M4_VLMAX;
  unsigned long active_vl = E64_NP2_VL;
  asm volatile(
      "vsetvli zero, %[full_vl], e64, m4, ta, ma\n"
      "vle64.v v0, (%[source])\n"
      "vsetvli zero, %[active_vl], e64, m4, ta, ma\n"
      "vslidedown.vi v28, v0, 15\n"
      "vse64.v v28, (%[result])\n"
      :
      : [full_vl] "r"(full_vl), [active_vl] "r"(active_vl),
        [source] "r"(slide_np2_source), [result] "r"(slide_np2_result)
      : "memory");
  wait_for_vector();

  for (unsigned index = 0; index < E64_NP2_VL; ++index) {
    uint64_t expected = slide_np2_source[index + 15];
    if (slide_np2_result[index] != expected) {
      printf("vslidedown NP2 atomic feedback failed at %d: got=%lx expected=%lx\n",
             index, slide_np2_result[index], expected);
      ++num_failed;
      break;
    }
  }
}

static void test_slideup_np2_aligned_word(void) {
  for (unsigned index = 0; index < E64_M2_VLMAX; ++index) {
    slide_np2_up_source[index] = 0x6100000000000000ull + 0x101ull * index;
    slide_np2_up_old[index] = 0xa100000000000000ull + 0x202ull * index;
  }

  unsigned long full_vl = E64_M2_VLMAX;
  unsigned long active_vl = E64_NP2_UP_VL;
  unsigned long offset = 12;
  asm volatile(
      "vsetvli zero, %[full_vl], e64, m2, tu, mu\n"
      "vle64.v v4, (%[source])\n"
      "vle64.v v20, (%[old])\n"
      "vsetvli zero, %[active_vl], e64, m2, tu, mu\n"
      "vslideup.vx v20, v4, %[offset]\n"
      "vse64.v v20, (%[result])\n"
      :
      : [full_vl] "r"(full_vl), [active_vl] "r"(active_vl),
        [offset] "r"(offset), [source] "r"(slide_np2_up_source),
        [old] "r"(slide_np2_up_old), [result] "r"(slide_np2_up_result)
      : "memory");
  wait_for_vector();

  for (unsigned index = 0; index < E64_NP2_UP_VL; ++index) {
    uint64_t expected = index < offset ? slide_np2_up_old[index]
                                       : slide_np2_up_source[index - offset];
    if (slide_np2_up_result[index] != expected) {
      printf("vslideup NP2 aligned-word failed at %d: got=%lx expected=%lx\n",
             index, slide_np2_up_result[index], expected);
      ++num_failed;
      break;
    }
  }
}

static void test_back_to_back_masked_slides(void) {
  for (unsigned index = 0; index < 15; ++index) {
    slide_pair_source[index] = 0x31000000u + 0x101u * index;
    slide_pair_old_down[index] = 0xa1000000u + 0x202u * index;
    slide_pair_old_up[index] = 0xb2000000u + 0x303u * index;
  }
  slide_pair_mask[0] = 0xb6;
  slide_pair_mask[1] = 0x35;

  asm volatile(
      "vsetivli zero, 15, e32, mf2, tu, mu\n"
      "vle32.v v8, (%[source])\n"
      "vle32.v v10, (%[old_down])\n"
      "vle32.v v12, (%[old_up])\n"
      "vlm.v v0, (%[mask])\n"
      // Keep the two masked slide requests adjacent.  Their mask streams must
      // remain associated with the corresponding SLDU issue contexts.
      "vslidedown.vi v10, v8, 6, v0.t\n"
      "vslideup.vi v12, v8, 2, v0.t\n"
      "vse32.v v10, (%[result_down])\n"
      "vse32.v v12, (%[result_up])\n"
      :
      : [source] "r"(slide_pair_source), [old_down] "r"(slide_pair_old_down),
        [old_up] "r"(slide_pair_old_up), [mask] "r"(slide_pair_mask),
        [result_down] "r"(slide_pair_result_down),
        [result_up] "r"(slide_pair_result_up)
      : "memory");
  wait_for_vector();

  for (unsigned index = 0; index < 15; ++index) {
    uint32_t expected_down = slide_pair_old_down[index];
    uint32_t expected_up = slide_pair_old_up[index];
    if (mask_bit(slide_pair_mask, index)) {
      expected_down = index + 6 < 15 ? slide_pair_source[index + 6] : 0;
      if (index >= 2)
        expected_up = slide_pair_source[index - 2];
    }
    if (slide_pair_result_down[index] != expected_down ||
        slide_pair_result_up[index] != expected_up) {
      printf("back-to-back masked slide failed at %d: down=%x/%x up=%x/%x mask=%d\n",
             index, slide_pair_result_down[index], expected_down,
             slide_pair_result_up[index], expected_up,
             mask_bit(slide_pair_mask, index));
      ++num_failed;
      break;
    }
  }
}

static void test_slidedown_byte_offset_overflow(void) {
  for (unsigned index = 0; index < E64_M1_VLMAX; ++index) {
    slide_overflow_source[index] = 0x7100000000000000ull + index;
    slide_overflow_old[index] = 0xc100000000000000ull + index;
  }

  unsigned long full_vl = E64_M1_VLMAX;
  unsigned long active_vl = E64_OVERFLOW_VL;
  unsigned long offset = 1ull << 62;
  asm volatile(
      "vsetvli zero, %[full_vl], e64, m1, tu, mu\n"
      "vle64.v v8, (%[source])\n"
      "vle64.v v4, (%[old])\n"
      "vsetvli zero, %[active_vl], e64, m1, tu, mu\n"
      "vslidedown.vx v4, v8, %[offset]\n"
      "vsetvli zero, %[full_vl], e64, m1, tu, mu\n"
      "vse64.v v4, (%[result])\n"
      :
      : [full_vl] "r"(full_vl), [active_vl] "r"(active_vl),
        [offset] "r"(offset), [source] "r"(slide_overflow_source),
        [old] "r"(slide_overflow_old), [result] "r"(slide_overflow_result)
      : "memory");
  wait_for_vector();

  for (unsigned index = 0; index < E64_M1_VLMAX; ++index) {
    uint64_t expected = index < E64_OVERFLOW_VL ? 0 : slide_overflow_old[index];
    if (slide_overflow_result[index] == expected)
      continue;
    printf("vslidedown saturated offset failed at %d: got=%lx expected=%lx\n",
           index, slide_overflow_result[index], expected);
    ++num_failed;
    break;
  }
}

static void test_slidedown_whole_word_plus_one(void) {
  for (unsigned index = 0; index < E8_VL; ++index)
    source8[index] = (uint8_t)(0x19u + 37u * index);

  unsigned long source_vl = 128;
  unsigned long active_m2_vl = E8_RESIDUAL_M2_VL;
  unsigned long active_m8_vl = E8_RESIDUAL_M8_VL;
  unsigned long offset = E8_RESIDUAL_OFFSET;

  asm volatile(
      "vsetvli zero, %[source_vl], e8, m2, ta, ma\n"
      "vle8.v v8, (%[source])\n"
      "vsetvli zero, %[active_vl], e8, m2, ta, ma\n"
      "vslidedown.vx v12, v8, %[offset]\n"
      "vse8.v v12, (%[result])\n"
      :
      : [source_vl] "r"(source_vl), [active_vl] "r"(active_m2_vl),
        [offset] "r"(offset), [source] "r"(source8),
        [result] "r"(slide_residual_m2_result)
      : "memory");
  wait_for_vector();

  for (unsigned index = 0; index < E8_RESIDUAL_M2_VL; ++index) {
    uint8_t expected = source8[index + E8_RESIDUAL_OFFSET];
    if (slide_residual_m2_result[index] == expected)
      continue;
    printf("vslidedown e8,m2 offset33 failed at %d: got=%x expected=%x\n",
           index, slide_residual_m2_result[index], expected);
    ++num_failed;
    break;
  }

  asm volatile(
      "vsetvli zero, %[source_vl], e8, m8, ta, ma\n"
      "vle8.v v0, (%[source])\n"
      "vsetvli zero, %[active_vl], e8, m8, ta, ma\n"
      "vslidedown.vx v8, v0, %[offset]\n"
      "vse8.v v8, (%[result])\n"
      :
      : [source_vl] "r"(source_vl), [active_vl] "r"(active_m8_vl),
        [offset] "r"(offset), [source] "r"(source8),
        [result] "r"(slide_residual_m8_result)
      : "memory");
  wait_for_vector();

  for (unsigned index = 0; index < E8_RESIDUAL_M8_VL; ++index) {
    uint8_t expected = source8[index + E8_RESIDUAL_OFFSET];
    if (slide_residual_m8_result[index] == expected)
      continue;
    printf("vslidedown e8,m8 offset33 failed at %d: got=%x expected=%x\n",
           index, slide_residual_m8_result[index], expected);
    ++num_failed;
    break;
  }
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  test_e16_m4_partial_word();
  test_e8_m8_whole_word();
  test_slidedown_partial_tail_undisturbed();
  test_slide1down_dependent_read();
  test_slide_result_queue_boundary();
  test_slidedown_np2_atomic_feedback();
  test_slideup_np2_aligned_word();
  test_back_to_back_masked_slides();
  test_slidedown_byte_offset_overflow();
  test_slidedown_whole_word_plus_one();
  EXIT_CHECK();
}
