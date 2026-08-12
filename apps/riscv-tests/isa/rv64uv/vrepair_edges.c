// Boundary regressions for widening, narrowing, and reduction datapaths.

#include "vector_macros.h"

#define ELEMENTS 8

static uint8_t narrow_a[ELEMENTS] __attribute__((aligned(128))) = {
    0x00, 0x01, 0x7f, 0x80, 0xfe, 0xff, 0x55, 0xaa};
static uint8_t narrow_b[ELEMENTS] __attribute__((aligned(128))) = {
    0x01, 0xff, 0x01, 0x80, 0x02, 0xff, 0xaa, 0x55};
static uint16_t wide_result[ELEMENTS] __attribute__((aligned(128)));
static int16_t wide_signed_source16[ELEMENTS] __attribute__((aligned(128))) = {
    0, 1, 127, 128, -1, -128, 0x5555, -0x5555};
static int32_t wide_signed_source32[ELEMENTS] __attribute__((aligned(128))) = {
    0, 1, 32767, 32768, -1, -32768, 0x55555555, -0x55555555};
static int64_t wide_signed_source64[ELEMENTS] __attribute__((aligned(128))) = {
    0, 1, INT32_MAX, (int64_t)INT32_MAX + 1, -1, INT32_MIN,
    INT64_C(0x5555555555555555), -INT64_C(0x5555555555555555)};
static uint32_t wide_result32[ELEMENTS] __attribute__((aligned(128)));
static uint64_t wide_result64[ELEMENTS] __attribute__((aligned(128)));
static uint16_t clip_source[ELEMENTS] __attribute__((aligned(128))) = {
    0, 1, 254, 255, 256, 511, 0x7fff, 0xffff};
static uint8_t clip_result[ELEMENTS] __attribute__((aligned(128)));
static uint32_t clip_source32[ELEMENTS] __attribute__((aligned(128))) = {
    0, 1, 0xfffe, 0xffff, 0x10000, 0x1ffff, 0x7fffffff, 0xffffffff};
static uint64_t clip_source64[ELEMENTS] __attribute__((aligned(128))) = {
    0, 1, UINT32_MAX - 1, UINT32_MAX, (uint64_t)UINT32_MAX + 1,
    UINT64_C(0x1ffffffff), INT64_MAX, UINT64_MAX};
static uint16_t clip_result16[ELEMENTS] __attribute__((aligned(128)));
static uint32_t clip_result32[ELEMENTS] __attribute__((aligned(128)));
static int16_t signed_clip_source16[ELEMENTS] __attribute__((aligned(128))) = {
    INT16_MIN, -257, -256, -129, -128, 127, 128, INT16_MAX};
static int32_t signed_clip_source32[ELEMENTS] __attribute__((aligned(128))) = {
    INT32_MIN, -65537, -65536, -32769, -32768, 32767, 32768, INT32_MAX};
static int64_t signed_clip_source64[ELEMENTS] __attribute__((aligned(128))) = {
    INT64_MIN, -INT64_C(4294967297), -INT64_C(4294967296),
    -INT64_C(2147483649), INT32_MIN, INT32_MAX,
    INT64_C(2147483648), INT64_MAX};
static int8_t signed_clip_result8[ELEMENTS] __attribute__((aligned(128)));
static int16_t signed_clip_result16[ELEMENTS] __attribute__((aligned(128)));
static int32_t signed_clip_result32[ELEMENTS] __attribute__((aligned(128)));
static uint32_t reduction_source[ELEMENTS] __attribute__((aligned(128))) = {
    0, 1, 0xffffffff, 0x80000000, 4, 5, 6, 7};
static uint32_t reduction_seed[4] __attribute__((aligned(128))) = {
    0x12345678, 0, 0, 0};
static uint32_t reduction_result[4] __attribute__((aligned(128)));
static uint8_t reshuffle_data[4 * 128] __attribute__((aligned(128)));
static uint8_t reshuffle_shift[4 * 128] __attribute__((aligned(128)));
static uint16_t reshuffle_result[256] __attribute__((aligned(128)));
static uint16_t inplace_source16[512] __attribute__((aligned(128)));
static uint32_t inplace_result32[256] __attribute__((aligned(128)));
static uint16_t whole_move_source16[256] __attribute__((aligned(128)));
static uint32_t whole_move_source32[128] __attribute__((aligned(128)));
static uint16_t whole_move_result16[256] __attribute__((aligned(128)));
static uint32_t whole_move_result32[128] __attribute__((aligned(128)));
static uint8_t scalar_extract_source[128] __attribute__((aligned(128)));
#define PARTIAL_LANE_ELEMENTS 93
static uint64_t partial_fma_zero[PARTIAL_LANE_ELEMENTS] __attribute__((aligned(128)));
static uint64_t partial_fma_addend[PARTIAL_LANE_ELEMENTS] __attribute__((aligned(128)));
static uint64_t partial_fma_result[PARTIAL_LANE_ELEMENTS] __attribute__((aligned(128)));

static void wait_for_vector(void) {
  unsigned long vl;
  asm volatile("csrr %0, vl\n fence rw, rw" : "=r"(vl) :: "memory");
}

static int8_t saturate_i8(int16_t value) {
  if (value > INT8_MAX) return INT8_MAX;
  if (value < INT8_MIN) return INT8_MIN;
  return (int8_t)value;
}

static int16_t saturate_i16(int32_t value) {
  if (value > INT16_MAX) return INT16_MAX;
  if (value < INT16_MIN) return INT16_MIN;
  return (int16_t)value;
}

static int32_t saturate_i32(int64_t value) {
  if (value > INT32_MAX) return INT32_MAX;
  if (value < INT32_MIN) return INT32_MIN;
  return (int32_t)value;
}

static unsigned rounding_increment(uint64_t value, unsigned shift,
                                   unsigned vxrm) {
  if (shift == 0) return 0;
  unsigned round_bit = (value >> (shift - 1)) & 1;
  unsigned retained_lsb = (value >> shift) & 1;
  uint64_t lower_mask = shift == 1 ? 0 : ((UINT64_C(1) << (shift - 1)) - 1);
  unsigned lower_nonzero = (value & lower_mask) != 0;
  switch (vxrm) {
    case 0: return round_bit;
    case 1: return round_bit && (lower_nonzero || retained_lsb);
    case 2: return 0;
    default: return !retained_lsb && (round_bit || lower_nonzero);
  }
}

static void test_widening(void) {
  asm volatile(
      "vsetvli zero, %[vl], e8, m1, tu, mu\n"
      "vle8.v v8, (%[a])\n"
      "vle8.v v9, (%[b])\n"
      "vwaddu.vv v10, v8, v9\n"
      "vse16.v v10, (%[out])\n"
      :
      : [vl] "r"(ELEMENTS), [a] "r"(narrow_a), [b] "r"(narrow_b),
        [out] "r"(wide_result)
      : "memory");
  wait_for_vector();
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    uint16_t expected = (uint16_t)narrow_a[index] + narrow_b[index];
    if (wide_result[index] != expected) {
      printf("widening vv failed at %d: got=%x expected=%x\n", index,
             wide_result[index], expected);
      ++num_failed;
      break;
    }
  }

  long scalar = -1;
  asm volatile(
      "vsetvli zero, %[vl], e8, m1, tu, mu\n"
      "vle16.v v8, (%[a])\n"
      "vwadd.wx v10, v8, %[scalar]\n"
      "vse16.v v10, (%[out])\n"
      :
      : [vl] "r"(ELEMENTS), [a] "r"(wide_signed_source16), [scalar] "r"(scalar),
        [out] "r"(wide_result)
      : "memory");
  wait_for_vector();
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    int16_t expected = wide_signed_source16[index] - 1;
    if ((int16_t)wide_result[index] != expected) {
      printf("widening wx failed at %d: got=%x expected=%x\n", index,
             wide_result[index], (uint16_t)expected);
      ++num_failed;
      break;
    }
  }

  asm volatile(
      "vsetvli zero, %[vl], e16, m1, tu, mu\n"
      "vle32.v v8, (%[a])\n"
      "vwadd.wx v10, v8, %[scalar]\n"
      "vse32.v v10, (%[out])\n"
      :
      : [vl] "r"(ELEMENTS), [a] "r"(wide_signed_source32), [scalar] "r"(scalar),
        [out] "r"(wide_result32)
      : "memory");
  wait_for_vector();
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    int32_t expected = wide_signed_source32[index] - 1;
    if ((int32_t)wide_result32[index] != expected) {
      printf("widening wx e16 failed at %d: got=%x expected=%x\n", index,
             wide_result32[index], (uint32_t)expected);
      ++num_failed;
      break;
    }
  }

  asm volatile(
      "vsetvli zero, %[vl], e32, m1, tu, mu\n"
      "vle64.v v8, (%[a])\n"
      "vwadd.wx v10, v8, %[scalar]\n"
      "vse64.v v10, (%[out])\n"
      :
      : [vl] "r"(ELEMENTS), [a] "r"(wide_signed_source64), [scalar] "r"(scalar),
        [out] "r"(wide_result64)
      : "memory");
  wait_for_vector();
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    int64_t expected = wide_signed_source64[index] - 1;
    if ((int64_t)wide_result64[index] != expected) {
      printf("widening wx e32 failed at %d: got=%lx expected=%lx\n", index,
             wide_result64[index], (uint64_t)expected);
      ++num_failed;
      break;
    }
  }

  // The unsigned .wx forms must truncate rs1 to the narrow source SEW before
  // zero-extending it to the widened datapath. A scalar value of -1 exposes
  // accidental XLEN-wide extension at every supported source SEW.
  asm volatile(
      "vsetvli zero, %[vl], e8, m1, tu, mu\n"
      "vle16.v v8, (%[a])\n"
      "vwaddu.wx v10, v8, %[scalar]\n"
      "vse16.v v10, (%[out])\n"
      :
      : [vl] "r"(ELEMENTS), [a] "r"(wide_signed_source16), [scalar] "r"(scalar),
        [out] "r"(wide_result)
      : "memory");
  wait_for_vector();
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    uint16_t expected = (uint16_t)wide_signed_source16[index] + UINT8_MAX;
    if (wide_result[index] != expected) {
      printf("widening unsigned wx e8 failed at %d: got=%x expected=%x\n",
             index, wide_result[index], expected);
      ++num_failed;
      break;
    }
  }

  asm volatile(
      "vsetvli zero, %[vl], e16, m1, tu, mu\n"
      "vle32.v v8, (%[a])\n"
      "vwaddu.wx v10, v8, %[scalar]\n"
      "vse32.v v10, (%[out])\n"
      :
      : [vl] "r"(ELEMENTS), [a] "r"(wide_signed_source32), [scalar] "r"(scalar),
        [out] "r"(wide_result32)
      : "memory");
  wait_for_vector();
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    uint32_t expected = (uint32_t)wide_signed_source32[index] + UINT16_MAX;
    if (wide_result32[index] != expected) {
      printf("widening unsigned wx e16 failed at %d: got=%x expected=%x\n",
             index, wide_result32[index], expected);
      ++num_failed;
      break;
    }
  }

  asm volatile(
      "vsetvli zero, %[vl], e32, m1, tu, mu\n"
      "vle64.v v8, (%[a])\n"
      "vwaddu.wx v10, v8, %[scalar]\n"
      "vse64.v v10, (%[out])\n"
      :
      : [vl] "r"(ELEMENTS), [a] "r"(wide_signed_source64), [scalar] "r"(scalar),
        [out] "r"(wide_result64)
      : "memory");
  wait_for_vector();
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    uint64_t expected = (uint64_t)wide_signed_source64[index] + UINT32_MAX;
    if (wide_result64[index] != expected) {
      printf("widening unsigned wx e32 failed at %d: got=%lx expected=%lx\n",
             index, wide_result64[index], expected);
      ++num_failed;
      break;
    }
  }
}

static void test_narrowing(void) {
  set_vxrm(2);
  reset_vxsat;
  asm volatile(
      "vsetvli zero, %[vl], e8, m1, tu, mu\n"
      "vle16.v v8, (%[input])\n"
      "vnclipu.wx v10, v8, zero\n"
      "vse8.v v10, (%[output])\n"
      :
      : [vl] "r"(ELEMENTS), [input] "r"(clip_source),
        [output] "r"(clip_result)
      : "memory");
  wait_for_vector();
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    uint8_t expected = clip_source[index] > 255 ? 255 : clip_source[index];
    if (clip_result[index] != expected) {
      printf("narrowing failed at %d: got=%x expected=%x\n", index,
             clip_result[index], expected);
      ++num_failed;
      break;
    }
  }

  asm volatile(
      "vsetvli zero, %[vl], e16, m1, tu, mu\n"
      "vle32.v v8, (%[input])\n"
      "vnclipu.wx v10, v8, zero\n"
      "vse16.v v10, (%[output])\n"
      :
      : [vl] "r"(ELEMENTS), [input] "r"(clip_source32),
        [output] "r"(clip_result16)
      : "memory");
  wait_for_vector();
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    uint16_t expected = clip_source32[index] > UINT16_MAX
                            ? UINT16_MAX : clip_source32[index];
    if (clip_result16[index] != expected) {
      printf("narrowing e16 failed at %d: got=%x expected=%x\n", index,
             clip_result16[index], expected);
      ++num_failed;
      break;
    }
  }

  asm volatile(
      "vsetvli zero, %[vl], e32, m1, tu, mu\n"
      "vle64.v v8, (%[input])\n"
      "vnclipu.wx v10, v8, zero\n"
      "vse32.v v10, (%[output])\n"
      :
      : [vl] "r"(ELEMENTS), [input] "r"(clip_source64),
        [output] "r"(clip_result32)
      : "memory");
  wait_for_vector();
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    uint32_t expected = clip_source64[index] > UINT32_MAX
                            ? UINT32_MAX : clip_source64[index];
    if (clip_result32[index] != expected) {
      printf("narrowing e32 failed at %d: got=%x expected=%x\n", index,
             clip_result32[index], expected);
      ++num_failed;
      break;
    }
  }
  uint64_t vxsat;
  read_vxsat(vxsat);
  if (vxsat != 1) {
    printf("narrowing saturation flag failed: got=%lx expected=1\n", vxsat);
    ++num_failed;
  }

  reset_vxsat;
  asm volatile(
      "vsetvli zero, %[vl], e8, m1, tu, mu\n"
      "vle16.v v8, (%[input])\n"
      "vnclip.wx v10, v8, zero\n"
      "vse8.v v10, (%[output])\n"
      :
      : [vl] "r"(ELEMENTS), [input] "r"(signed_clip_source16),
        [output] "r"(signed_clip_result8)
      : "memory");
  wait_for_vector();
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    int8_t expected = saturate_i8(signed_clip_source16[index]);
    if (signed_clip_result8[index] != expected) {
      printf("signed narrowing e8 failed at %d: got=%x expected=%x\n", index,
             (uint8_t)signed_clip_result8[index], (uint8_t)expected);
      ++num_failed;
      break;
    }
  }

  asm volatile(
      "vsetvli zero, %[vl], e16, m1, tu, mu\n"
      "vle32.v v8, (%[input])\n"
      "vnclip.wx v10, v8, zero\n"
      "vse16.v v10, (%[output])\n"
      :
      : [vl] "r"(ELEMENTS), [input] "r"(signed_clip_source32),
        [output] "r"(signed_clip_result16)
      : "memory");
  wait_for_vector();
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    int16_t expected = saturate_i16(signed_clip_source32[index]);
    if (signed_clip_result16[index] != expected) {
      printf("signed narrowing e16 failed at %d: got=%x expected=%x\n", index,
             (uint16_t)signed_clip_result16[index], (uint16_t)expected);
      ++num_failed;
      break;
    }
  }

  asm volatile(
      "vsetvli zero, %[vl], e32, m1, tu, mu\n"
      "vle64.v v8, (%[input])\n"
      "vnclip.wx v10, v8, zero\n"
      "vse32.v v10, (%[output])\n"
      :
      : [vl] "r"(ELEMENTS), [input] "r"(signed_clip_source64),
        [output] "r"(signed_clip_result32)
      : "memory");
  wait_for_vector();
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    int32_t expected = saturate_i32(signed_clip_source64[index]);
    if (signed_clip_result32[index] != expected) {
      printf("signed narrowing e32 failed at %d: got=%x expected=%x\n", index,
             (uint32_t)signed_clip_result32[index], (uint32_t)expected);
      ++num_failed;
      break;
    }
  }
  read_vxsat(vxsat);
  if (vxsat != 1) {
    printf("signed narrowing saturation flag failed: got=%lx expected=1\n", vxsat);
    ++num_failed;
  }

  // A one-bit shift exercises all four vxrm rules. Values around 0xff/0x100
  // also verify that rounding occurs before unsigned saturation.
  for (unsigned mode = 0; mode < 4; ++mode) {
    set_vxrm(mode);
    reset_vxsat;
    asm volatile(
        "vsetvli zero, %[vl], e8, m1, tu, mu\n"
        "vle16.v v8, (%[input])\n"
        "vnclipu.wi v10, v8, 1\n"
        "vse8.v v10, (%[output])\n"
        :
        : [vl] "r"(ELEMENTS), [input] "r"(clip_source),
          [output] "r"(clip_result)
        : "memory");
    wait_for_vector();
    for (unsigned index = 0; index < ELEMENTS; ++index) {
      uint32_t rounded = (clip_source[index] >> 1) +
                         rounding_increment(clip_source[index], 1, mode);
      uint8_t expected = rounded > UINT8_MAX ? UINT8_MAX : rounded;
      if (clip_result[index] != expected) {
        printf("narrowing rounding failed: vxrm=%d index=%d got=%x expected=%x\n",
               mode, index, clip_result[index], expected);
        ++num_failed;
        break;
      }
    }
    read_vxsat(vxsat);
    if (vxsat != 1) {
      printf("narrowing rounding vxsat failed: vxrm=%d got=%lx expected=1\n",
             mode, vxsat);
      ++num_failed;
    }
  }
}

static void test_group_reshuffle(void) {
  for (unsigned byte = 0; byte < sizeof(reshuffle_data); ++byte) {
    reshuffle_data[byte] = (uint8_t)(byte * 13u + 7u);
    reshuffle_shift[byte] = 1;
  }
  set_vxrm(2);
  asm volatile(
      "vsetvli zero, %[vl16], e16, m1, tu, mu\n"
      "vle16.v v20, (%[data])\n"
      "vle16.v v28, (%[shift])\n"
      "vsetvli zero, %[vl32], e32, m1, tu, mu\n"
      "vle32.v v21, (%[data1])\n"
      "vle32.v v29, (%[shift1])\n"
      "vsetvli zero, %[vl8], e8, m1, tu, mu\n"
      "vle8.v v22, (%[data2])\n"
      "vle8.v v30, (%[shift2])\n"
      "vsetvli zero, %[vl64], e64, m1, tu, mu\n"
      "vle64.v v23, (%[data3])\n"
      "vle64.v v31, (%[shift3])\n"
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vssrl.vv v8, v20, v28\n"
      "vse16.v v8, (%[output])\n"
      :
      : [vl8] "r"(128), [vl16] "r"(64), [vl32] "r"(32), [vl64] "r"(16),
        [vl] "r"(256), [data] "r"(reshuffle_data),
        [data1] "r"(reshuffle_data + 128), [data2] "r"(reshuffle_data + 256),
        [data3] "r"(reshuffle_data + 384), [shift] "r"(reshuffle_shift),
        [shift1] "r"(reshuffle_shift + 128), [shift2] "r"(reshuffle_shift + 256),
        [shift3] "r"(reshuffle_shift + 384), [output] "r"(reshuffle_result)
      : "memory");
  wait_for_vector();
  for (unsigned index = 0; index < 256; ++index) {
    uint16_t raw = (uint16_t)reshuffle_data[2 * index] |
                   ((uint16_t)reshuffle_data[2 * index + 1] << 8);
    uint16_t expected = raw >> 1;
    if (reshuffle_result[index] != expected) {
      printf("group reshuffle failed at %d: got=%x expected=%x\n", index,
             reshuffle_result[index], expected);
      ++num_failed;
      break;
    }
  }
}

static void test_inplace_group_reshuffle(void) {
  for (unsigned index = 0; index < 512; ++index)
    inplace_source16[index] = (uint16_t)(0x80u + 3u * index);

  asm volatile(
      "vsetvli zero, %[vl16], e16, m8, tu, mu\n"
      "vle16.v v24, (%[input])\n"
      "vsetvli zero, %[vl32], e32, m8, tu, mu\n"
      "vid.v v8\n"
      "vadd.vv v24, v24, v8\n"
      "vse32.v v24, (%[output])\n"
      :
      : [vl16] "r"(512), [vl32] "r"(256), [input] "r"(inplace_source16),
        [output] "r"(inplace_result32)
      : "memory");
  wait_for_vector();

  for (unsigned index = 0; index < 256; ++index) {
    uint32_t source = (uint32_t)inplace_source16[2 * index] |
                      ((uint32_t)inplace_source16[2 * index + 1] << 16);
    uint32_t expected = source + index;
    if (inplace_result32[index] != expected) {
      printf("in-place group reshuffle failed at %d: got=%x expected=%x\n",
             index, inplace_result32[index], expected);
      ++num_failed;
      break;
    }
  }
}

static void test_whole_move_mixed_layout(void) {
  for (unsigned index = 0; index < 256; ++index)
    whole_move_source16[index] = (uint16_t)(0x120u + 5u * index);
  for (unsigned index = 0; index < 128; ++index)
    whole_move_source32[index] = 0x81000000u + 0x101u * index;

  asm volatile(
      "vsetvli zero, %[vl16], e16, m4, tu, mu\n"
      "vle16.v v24, (%[source16])\n"
      "vsetvli zero, %[vl32], e32, m4, tu, mu\n"
      "vle32.v v28, (%[source32])\n"
      "vmv8r.v v8, v24\n"
      "vsetvli zero, %[vl16], e16, m4, tu, mu\n"
      "vse16.v v8, (%[result16])\n"
      "vsetvli zero, %[vl32], e32, m4, tu, mu\n"
      "vse32.v v12, (%[result32])\n"
      :
      : [vl16] "r"(256), [vl32] "r"(128),
        [source16] "r"(whole_move_source16),
        [source32] "r"(whole_move_source32),
        [result16] "r"(whole_move_result16),
        [result32] "r"(whole_move_result32)
      : "memory");
  wait_for_vector();

  for (unsigned index = 0; index < 256; ++index) {
    if (whole_move_result16[index] != whole_move_source16[index]) {
      printf("mixed-layout vmv8r e16 failed at %d: got=%x expected=%x\n",
             index, whole_move_result16[index], whole_move_source16[index]);
      ++num_failed;
      break;
    }
  }
  for (unsigned index = 0; index < 128; ++index) {
    if (whole_move_result32[index] != whole_move_source32[index]) {
      printf("mixed-layout vmv8r e32 failed at %d: got=%x expected=%x\n",
             index, whole_move_result32[index], whole_move_source32[index]);
      ++num_failed;
      break;
    }
  }
}

static void test_scalar_extract_cross_eew_alias(void) {
  for (unsigned index = 0; index < sizeof(scalar_extract_source); ++index)
    scalar_extract_source[index] = 0;
  scalar_extract_source[0] = 0x00;
  scalar_extract_source[1] = 0x05;

  unsigned long bits;
  unsigned long vl8 = 128;
  unsigned long vl16 = 64;
  unsigned long vl32 = 32;
  asm volatile(
      "vsetvli zero, %[vl8], e8, m1, tu, mu\n"
      "vle8.v v9, (%[source])\n"
      // Normalize the v8-v15 source group to e16. The scalar destination of
      // vfmv.f.s is fs1 (architectural index 9), numerically aliasing v9 but
      // not constituting a vector destination.
      "vsetvli zero, %[vl16], e16, m1, tu, mu\n"
      "vmv8r.v v0, v8\n"
      "vsetvli zero, %[vl32], e32, m2, tu, mu\n"
      "vfmv.f.s fs1, v9\n"
      "fmv.x.w %[bits], fs1\n"
      : [bits] "=r"(bits)
      : [source] "r"(scalar_extract_source), [vl8] "r"(vl8),
        [vl16] "r"(vl16), [vl32] "r"(vl32)
      : "fs1", "memory");
  wait_for_vector();

  if ((uint32_t)bits != 0x00000500u) {
    printf("cross-EEW vfmv.f.s alias failed: got=%x expected=500\n",
           (uint32_t)bits);
    ++num_failed;
  }
}

static void test_fp64_m8_partial_lane(void) {
  for (unsigned index = 0; index < PARTIAL_LANE_ELEMENTS; ++index) {
    partial_fma_zero[index] = 0;
    partial_fma_addend[index] = index;
    partial_fma_result[index] = UINT64_MAX;
  }

  asm volatile(
      "vsetvli zero, %[vl], e64, m8, tu, mu\n"
      "vle64.v v0, (%[zero])\n"
      "vle64.v v8, (%[zero])\n"
      "vle64.v v16, (%[addend])\n"
      "vfmadd.vv v0, v8, v16\n"
      "vse64.v v0, (%[result])\n"
      :
      : [vl] "r"(PARTIAL_LANE_ELEMENTS), [zero] "r"(partial_fma_zero),
        [addend] "r"(partial_fma_addend), [result] "r"(partial_fma_result)
      : "memory");
  wait_for_vector();

  for (unsigned index = 0; index < PARTIAL_LANE_ELEMENTS; ++index) {
    if (partial_fma_result[index] != partial_fma_addend[index]) {
      printf("FP64 m8 partial-lane vfmadd failed at %d: got=%lx expected=%lx\n",
             index, partial_fma_result[index], partial_fma_addend[index]);
      ++num_failed;
      break;
    }
  }
}

static void test_reduction(void) {
  asm volatile(
      "vsetvli zero, %[one], e32, m1, tu, mu\n"
      "vle32.v v5, (%[seed])\n"
      "vsetvli zero, %[vl], e32, m4, tu, mu\n"
      "vle32.v v8, (%[input])\n"
      "vredsum.vs v3, v8, v5\n"
      "vsetvli zero, %[one], e32, m1, tu, mu\n"
      "vse32.v v3, (%[output])\n"
      :
      : [one] "r"(1), [vl] "r"(ELEMENTS), [seed] "r"(reduction_seed),
        [input] "r"(reduction_source), [output] "r"(reduction_result)
      : "memory");
  wait_for_vector();
  uint32_t expected = reduction_seed[0];
  for (unsigned index = 0; index < ELEMENTS; ++index)
    expected += reduction_source[index];
  if (reduction_result[0] != expected) {
    printf("reduction failed: got=%x expected=%x\n", reduction_result[0], expected);
    ++num_failed;
  }
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  enable_fp();
  test_widening();
  test_narrowing();
  test_reduction();
  test_group_reshuffle();
  test_inplace_group_reshuffle();
  test_whole_move_mixed_layout();
  test_scalar_extract_cross_eew_alias();
  test_fp64_m8_partial_lane();
  EXIT_CHECK();
}
