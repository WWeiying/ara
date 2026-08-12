// Reduction regression with older VALU work and a following masked slide.

#include "vector_macros.h"

#define LOAD_VL 16
#define WORK_VL 7
#define WIDEN_OVERLAP_VL 192
#define WIDEN_MASK_READ_VL 79
#define SLIDE_WAW_VL 106

static uint16_t compress_source[LOAD_VL] __attribute__((aligned(128)));
static uint8_t compress_mask[(LOAD_VL + 7) / 8] __attribute__((aligned(128)));
static uint16_t shift_source[LOAD_VL] __attribute__((aligned(128)));
static uint16_t reduction_source[LOAD_VL] __attribute__((aligned(128)));
static uint16_t reduction_seed[LOAD_VL] __attribute__((aligned(128)));
static uint16_t slide_source[LOAD_VL] __attribute__((aligned(128)));
static uint16_t slide_old[LOAD_VL] __attribute__((aligned(128)));
static uint16_t reduction_result[WORK_VL] __attribute__((aligned(128)));
static uint16_t slide_result[WORK_VL] __attribute__((aligned(128)));
static int16_t widening_overlap_source[WIDEN_OVERLAP_VL]
    __attribute__((aligned(128)));
static uint8_t widening_overlap_mask[(WIDEN_OVERLAP_VL + 7) / 8]
    __attribute__((aligned(128)));
static int32_t widening_overlap_seed __attribute__((aligned(128))) = -7;
static int32_t widening_overlap_result __attribute__((aligned(128)));
static uint64_t widening_mask_old[16] __attribute__((aligned(128)));
static int16_t widening_mask_source[WIDEN_MASK_READ_VL]
    __attribute__((aligned(128)));
static int32_t widening_mask_seed __attribute__((aligned(128))) = 0x1234;
static uint16_t widening_group_old[256] __attribute__((aligned(128)));
static uint64_t slide_waw_sqrt_source[SLIDE_WAW_VL]
    __attribute__((aligned(128)));
static uint64_t slide_waw_zero_source[SLIDE_WAW_VL]
    __attribute__((aligned(128)));
static uint64_t slide_waw_seed __attribute__((aligned(128))) =
    0x8000000000000000ull;
static uint64_t slide_waw_result __attribute__((aligned(128)));
static uint32_t short_ordered_source[2] __attribute__((aligned(128))) = {
    0x3f800000u, 0x40000000u};
static uint64_t short_ordered_seed __attribute__((aligned(128))) =
    UINT64_C(0x4010000000000000);
static uint64_t short_ordered_result __attribute__((aligned(128)));
static uint32_t short_min_source[2] __attribute__((aligned(128))) = {
    0x40400000u, 0xc0000000u};
static uint32_t short_min_seed __attribute__((aligned(128))) = 0x40a00000u;
static uint32_t short_min_result __attribute__((aligned(128)));

static void wait_for_vector(void) {
  unsigned long vl;
  asm volatile("csrr %0, vl\n fence rw, rw" : "=r"(vl) :: "memory");
}

static void test_reduction_after_older_valu(void) {
  for (unsigned index = 0; index < LOAD_VL; ++index) {
    compress_source[index] = (uint16_t)(0x3100u + 19u * index);
    shift_source[index] = (uint16_t)(0x1200u + 7u * index);
    reduction_source[index] = (uint16_t)(0xfffdu - 0x111u * index);
    reduction_seed[index] = (uint16_t)(0xa55au ^ (0x0101u * index));
    slide_source[index] = (uint16_t)(0x5100u + 23u * index);
    slide_old[index] = (uint16_t)(0xc100u + 13u * index);
  }

  // vssrl.vi produces 0x55 in the low byte of v0.  The following masked
  // slide therefore updates active elements 0, 2, 4, and 6.
  shift_source[0] = 0x02a8u;
  compress_mask[0] = 0x55u;
  compress_mask[1] = 0xaau;

  asm volatile(
      "vsetvli zero, %[load_vl], e16, m1, tu, mu\n"
      "vle16.v v16, (%[compress_source])\n"
      "vlm.v v8, (%[compress_mask])\n"
      "vle16.v v18, (%[shift_source])\n"
      "vle16.v v11, (%[reduction_source])\n"
      "vle16.v v9, (%[reduction_seed])\n"
      "vle16.v v5, (%[slide_source])\n"
      "vle16.v v20, (%[slide_old])\n"
      "vsetvli zero, %[work_vl], e16, m1, tu, mu\n"
      // Keep two normal VALU instructions ahead of the reduction.  The
      // reduction may enter its dedicated state only after both commit.
      "vcompress.vm v24, v16, v8\n"
      "vssrl.vi v0, v18, 3\n"
      // Destination/seed aliasing is legal and matches the random failure.
      "vredand.vs v9, v11, v9\n"
      "vslidedown.vi v20, v5, 6, v0.t\n"
      "vse16.v v9, (%[reduction_result])\n"
      "vse16.v v20, (%[slide_result])\n"
      :
      : [load_vl] "r"(LOAD_VL), [work_vl] "r"(WORK_VL),
        [compress_source] "r"(compress_source),
        [compress_mask] "r"(compress_mask), [shift_source] "r"(shift_source),
        [reduction_source] "r"(reduction_source),
        [reduction_seed] "r"(reduction_seed), [slide_source] "r"(slide_source),
        [slide_old] "r"(slide_old), [reduction_result] "r"(reduction_result),
        [slide_result] "r"(slide_result)
      : "memory");
  wait_for_vector();

  uint16_t expected_reduction = reduction_seed[0];
  for (unsigned index = 0; index < WORK_VL; ++index)
    expected_reduction &= reduction_source[index];

  if (reduction_result[0] != expected_reduction) {
    printf("queued vredand failed: got=%x expected=%x\n", reduction_result[0],
           expected_reduction);
    ++num_failed;
  }

  const uint8_t slide_mask = 0x55u;
  for (unsigned index = 0; index < WORK_VL; ++index) {
    uint16_t expected = (slide_mask >> index) & 1
                            ? slide_source[index + 6]
                            : slide_old[index];
    if (slide_result[index] != expected) {
      printf("slide after reduction failed at %d: got=%x expected=%x\n", index,
             slide_result[index], expected);
      ++num_failed;
      break;
    }
  }
}

static void test_widening_reduction_vd_source_overlap(void) {
  for (unsigned index = 0; index < WIDEN_OVERLAP_VL; ++index)
    widening_overlap_source[index] = 1;
  for (unsigned index = 0; index < sizeof(widening_overlap_mask); ++index)
    widening_overlap_mask[index] = 0xffu;

  asm volatile(
      "vsetivli zero, 1, e32, m1, ta, ma\n"
      "vle32.v v23, (%[seed])\n"
      "vsetvli zero, %[vl], e16, m4, ta, ma\n"
      "vle16.v v24, (%[source])\n"
      "vlm.v v0, (%[mask])\n"
      // v26 is a single-register, 2*SEW result inside the e16,m4 source
      // group v24-v27.  VL=192 makes v26 contain live source elements, so
      // this checks both the legal register overlap and read-before-write.
      "vwredsum.vs v26, v24, v23, v0.t\n"
      "vsetivli zero, 1, e32, m1, ta, ma\n"
      "vse32.v v26, (%[result])\n"
      :
      : [vl] "r"(WIDEN_OVERLAP_VL), [source] "r"(widening_overlap_source),
        [mask] "r"(widening_overlap_mask), [seed] "r"(&widening_overlap_seed),
        [result] "r"(&widening_overlap_result)
      : "memory");
  wait_for_vector();

  const int32_t expected = widening_overlap_seed + WIDEN_OVERLAP_VL;
  if (widening_overlap_result != expected) {
    printf("widening reduction vd/source overlap failed: got=%x expected=%x\n",
           (uint32_t)widening_overlap_result, (uint32_t)expected);
    ++num_failed;
  }
}

static unsigned popcount64(uint64_t value) {
  unsigned count = 0;
  while (value != 0) {
    count += value & 1u;
    value >>= 1;
  }
  return count;
}

static void test_widening_reduction_then_mask_read(void) {
  widening_mask_old[0] = 0x0123456789abcdefull;
  widening_mask_old[1] = 0xfedcba9876543210ull;
  for (unsigned index = 2; index < 16; ++index)
    widening_mask_old[index] = 0x1111111111111111ull * index;
  for (unsigned index = 0; index < WIDEN_MASK_READ_VL; ++index)
    widening_mask_source[index] = 1;

  unsigned long actual;
  asm volatile(
      "vsetivli zero, 16, e64, m1, ta, ma\n"
      "vle64.v v19, (%[old])\n"
      "vsetivli zero, 1, e32, m1, tu, mu\n"
      "vle32.v v8, (%[seed])\n"
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vle16.v v20, (%[source])\n"
      // Only the low 32-bit reduction result is written to v19.  The rest
      // of the register remains the raw e64-loaded state under tu policy.
      "vwredsum.vs v19, v20, v8\n"
      "vcpop.m %[actual], v19\n"
      : [actual] "=r"(actual)
      : [vl] "r"(WIDEN_MASK_READ_VL), [old] "r"(widening_mask_old),
        [seed] "r"(&widening_mask_seed), [source] "r"(widening_mask_source)
      : "memory");

  uint32_t reduction =
      (uint32_t)(widening_mask_seed + WIDEN_MASK_READ_VL);
  uint64_t low_word =
      (widening_mask_old[0] & 0xffffffff00000000ull) | reduction;
  unsigned expected = popcount64(low_word) +
                      popcount64(widening_mask_old[1] & 0x7fffull);
  if (actual != expected) {
    printf("widening reduction mask read failed: got=%lx expected=%x\n",
           actual, expected);
    ++num_failed;
  }
}

static void test_widening_reduction_group_tail_mask_read(void) {
  for (unsigned index = 0; index < 256; ++index)
    widening_group_old[index] = (uint16_t)(0x8041u + 0x101u * index);
  for (unsigned index = 0; index < WIDEN_MASK_READ_VL; ++index)
    widening_mask_source[index] = 1;

  unsigned long actual;
  asm volatile(
      "vsetvli zero, %[group_vl], e16, m4, ta, ma\n"
      "vle16.v v16, (%[old])\n"
      "vsetivli zero, 1, e32, m1, tu, mu\n"
      "vle32.v v8, (%[seed])\n"
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vle16.v v20, (%[source])\n"
      // v19 is the last physical register of the old e16,m4 group.  The
      // widening reduction changes only its low 32 bits and must preserve
      // the remaining architectural bits under tail-undisturbed policy.
      "vwredsum.vs v19, v20, v8\n"
      "vcpop.m %[actual], v19\n"
      : [actual] "=r"(actual)
      : [group_vl] "r"(256), [vl] "r"(WIDEN_MASK_READ_VL),
        [old] "r"(widening_group_old), [seed] "r"(&widening_mask_seed),
        [source] "r"(widening_mask_source)
      : "memory");

  uint32_t reduction =
      (uint32_t)(widening_mask_seed + WIDEN_MASK_READ_VL);
  const uint16_t *old_v19 = &widening_group_old[192];
  uint64_t low_word = ((uint64_t)old_v19[3] << 48) |
                      ((uint64_t)old_v19[2] << 32) | reduction;
  unsigned expected = popcount64(low_word) +
                      popcount64(((uint64_t)old_v19[4]) & 0x7fffull);
  if (actual != expected) {
    printf("widening reduction group-tail mask read failed: got=%lx "
           "expected=%x\n",
           actual, expected);
    ++num_failed;
  }
}

static void test_group_tail_after_mixed_eew_write(void) {
  for (unsigned index = 0; index < 256; ++index)
    widening_group_old[index] = (uint16_t)(0x8041u + 0x101u * index);
  for (unsigned index = 0; index < WIDEN_MASK_READ_VL; ++index)
    widening_mask_source[index] = 1;

  unsigned long actual;
  asm volatile(
      "vsetvli zero, %[group_vl], e16, m4, ta, ma\n"
      "vle16.v v16, (%[old])\n"
      "vsetivli zero, 1, e32, m1, tu, mu\n"
      "vle32.v v8, (%[seed])\n"
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vle16.v v20, (%[source])\n"
      "vwredsum.vs v19, v20, v8\n"
      "vmset.m v0\n"
      // Only v16 and the low part of v17 contain body elements at VL=79.
      // v19 is entirely tail and must retain both its data and interpretation.
      "vxor.vx v16, v20, zero, v0.t\n"
      "vcpop.m %[actual], v19\n"
      : [actual] "=r"(actual)
      : [group_vl] "r"(256), [vl] "r"(WIDEN_MASK_READ_VL),
        [old] "r"(widening_group_old), [seed] "r"(&widening_mask_seed),
        [source] "r"(widening_mask_source)
      : "memory");

  uint32_t reduction =
      (uint32_t)(widening_mask_seed + WIDEN_MASK_READ_VL);
  const uint16_t *old_v19 = &widening_group_old[192];
  uint64_t low_word = ((uint64_t)old_v19[3] << 48) |
                      ((uint64_t)old_v19[2] << 32) | reduction;
  unsigned expected = popcount64(low_word) +
                      popcount64(((uint64_t)old_v19[4]) & 0x7fffull);
  if (actual != expected) {
    printf("mixed-EEW group tail preservation failed: got=%lx expected=%x\n",
           actual, expected);
    ++num_failed;
  }
}

static void test_slow_mfpu_writer_before_slide(void) {
  for (unsigned index = 0; index < SLIDE_WAW_VL; ++index) {
    // Positive finite FP64 values keep the older square-root writer busy and
    // make any late overwrite distinguishable from the younger zeroing slide.
    slide_waw_sqrt_source[index] = 0x4010000000000000ull;
    slide_waw_zero_source[index] = 0;
  }
  slide_waw_result = ~0ull;

  asm volatile(
      "vsetivli zero, 1, e64, m1, ta, ma\n"
      "vle64.v v10, (%[seed])\n"
      "vsetvli zero, %[vl], e64, m8, tu, mu\n"
      "vle64.v v16, (%[sqrt_source])\n"
      "vle64.v v24, (%[zero_source])\n"
      // The slide writes the same destination group as the older, long-latency
      // MFPU instruction. Its writes must not overtake the older WAW producer.
      "vfsqrt.v v0, v16\n"
      "vslidedown.vx v0, v24, zero\n"
      "vfredmax.vs v8, v0, v10\n"
      "vsetivli zero, 1, e64, m1, ta, ma\n"
      "vse64.v v8, (%[result])\n"
      :
      : [vl] "r"(SLIDE_WAW_VL), [sqrt_source] "r"(slide_waw_sqrt_source),
        [zero_source] "r"(slide_waw_zero_source), [seed] "r"(&slide_waw_seed),
        [result] "r"(&slide_waw_result)
      : "memory");
  wait_for_vector();

  if (slide_waw_result != 0) {
    printf("slow-writer/slide WAW failed: got=%lx expected=0\n",
           slide_waw_result);
    ++num_failed;
  }
}

static void test_short_ordered_then_fp_reduction(void) {
  asm volatile(
      "vsetivli zero, 1, e64, m1, tu, mu\n"
      "vle64.v v18, (%[ordered_seed])\n"
      "vsetivli zero, 1, e32, m1, tu, mu\n"
      "vle32.v v23, (%[min_seed])\n"
      "vsetvli zero, %[vl], e32, m4, tu, mu\n"
      "vle32.v v20, (%[ordered_source])\n"
      "vle32.v v28, (%[min_source])\n"
      // With VL smaller than the lane count, the ordered reduction has no
      // local elements in lanes 2 and 3.  Its local completion must not retire
      // the selector reserved by the immediately following FP reduction.
      "vfwredosum.vs v10, v20, v18\n"
      "vfredmin.vs v23, v28, v23\n"
      "vsetivli zero, 1, e64, m1, tu, mu\n"
      "vse64.v v10, (%[ordered_result])\n"
      "vsetivli zero, 1, e32, m1, tu, mu\n"
      "vse32.v v23, (%[min_result])\n"
      :
      : [vl] "r"(2), [ordered_source] "r"(short_ordered_source),
        [ordered_seed] "r"(&short_ordered_seed),
        [ordered_result] "r"(&short_ordered_result),
        [min_source] "r"(short_min_source), [min_seed] "r"(&short_min_seed),
        [min_result] "r"(&short_min_result)
      : "memory");
  wait_for_vector();

  if (short_ordered_result != UINT64_C(0x401c000000000000)) {
    printf("short ordered reduction failed: got=%lx expected=401c000000000000\n",
           short_ordered_result);
    ++num_failed;
  }
  if (short_min_result != 0xc0000000u) {
    printf("FP reduction after short ordered reduction failed: got=%x "
           "expected=c0000000\n",
           short_min_result);
    ++num_failed;
  }
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  enable_fp();
  test_reduction_after_older_valu();
  test_widening_reduction_vd_source_overlap();
  test_widening_reduction_then_mask_read();
  test_widening_reduction_group_tail_mask_read();
  test_group_tail_after_mixed_eew_write();
  test_slow_mfpu_writer_before_slide();
  test_short_ordered_then_fp_reduction();
  EXIT_CHECK();
}
