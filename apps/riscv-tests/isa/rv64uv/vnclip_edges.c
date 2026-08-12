// Directed VNCLIP regressions for vector shift operands and uneven lane tails.

#include "vector_macros.h"

#define MAX_ELEMENTS 96

static int32_t signed_source[MAX_ELEMENTS] __attribute__((aligned(128)));
static uint32_t unsigned_source[MAX_ELEMENTS] __attribute__((aligned(128)));
static uint16_t shifts[MAX_ELEMENTS] __attribute__((aligned(128)));
static int16_t background[MAX_ELEMENTS] __attribute__((aligned(128)));
static int16_t signed_result[MAX_ELEMENTS] __attribute__((aligned(128)));
static uint16_t unsigned_result[MAX_ELEMENTS] __attribute__((aligned(128)));
static uint8_t mask_bits[(MAX_ELEMENTS + 7) / 8] __attribute__((aligned(128)));
static uint8_t overlap_bytes[MAX_ELEMENTS * sizeof(int32_t)] __attribute__((aligned(128)));
static uint16_t overlap_source_e16[2 * MAX_ELEMENTS] __attribute__((aligned(128)));
static int8_t triple_overlap_initial[256] __attribute__((aligned(128)));
static int8_t triple_overlap_result[256] __attribute__((aligned(128)));

static int16_t saturate_i16(int32_t value) {
  if (value > INT16_MAX) return INT16_MAX;
  if (value < INT16_MIN) return INT16_MIN;
  return (int16_t)value;
}

static void initialize_data(void) {
  for (unsigned i = 0; i < MAX_ELEMENTS; ++i) {
    int32_t magnitude = (int32_t)(0x1234 + i * 0x11111);
    signed_source[i] = (i & 1) ? -magnitude : magnitude;
    unsigned_source[i] = 0x1000u + i * 0x23456u;
    shifts[i] = (uint16_t)((i * 3 + 1) & 0xf);
    background[i] = (int16_t)(0x5000 + i);
    signed_result[i] = 0;
    unsigned_result[i] = 0;
  }

  for (unsigned i = 0; i < sizeof(mask_bits); ++i) mask_bits[i] = 0;
  for (unsigned i = 0; i < MAX_ELEMENTS; ++i) {
    if ((i % 5) != 1) mask_bits[i / 8] |= (uint8_t)(1u << (i % 8));
  }
}

static void test_signed_masked_vl30(void) {
  const unsigned vl = 30;
  asm volatile(
      "vsetvli zero, %[vl], e16, m2, tu, mu\n"
      "vle32.v v24, (%[source])\n"
      "vle16.v v4, (%[shifts])\n"
      "vle16.v v12, (%[background])\n"
      "vlm.v v0, (%[mask])\n"
      "csrwi vxrm, 2\n"
      "vnclip.wv v12, v24, v4, v0.t\n"
      "vse16.v v12, (%[result])\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(vl), [source] "r"(signed_source), [shifts] "r"(shifts),
        [background] "r"(background), [mask] "r"(mask_bits),
        [result] "r"(signed_result)
      : "memory");

  for (unsigned i = 0; i < vl; ++i) {
    int16_t expected = background[i];
    if ((mask_bits[i / 8] >> (i % 8)) & 1)
      expected = saturate_i16(signed_source[i] >> (shifts[i] & 0x1f));
    if (signed_result[i] != expected) {
      printf("vnclip.wv e16,m2,vl30 failed at %d: got=%x expected=%x\n",
             i, (uint16_t)signed_result[i], (uint16_t)expected);
      ++num_failed;
      return;
    }
  }
}

static void test_unsigned_unmasked_vl29(void) {
  const unsigned vl = 29;
  asm volatile(
      "vsetvli zero, %[vl], e16, m2, tu, mu\n"
      "vle32.v v24, (%[source])\n"
      "vle16.v v4, (%[shifts])\n"
      "csrwi vxrm, 2\n"
      "vnclipu.wv v12, v24, v4\n"
      "vse16.v v12, (%[result])\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(vl), [source] "r"(unsigned_source), [shifts] "r"(shifts),
        [result] "r"(unsigned_result)
      : "memory");

  for (unsigned i = 0; i < vl; ++i) {
    uint32_t shifted = unsigned_source[i] >> (shifts[i] & 0x1f);
    uint16_t expected = shifted > UINT16_MAX ? UINT16_MAX : (uint16_t)shifted;
    if (unsigned_result[i] != expected) {
      printf("vnclipu.wv e16,m2,vl29 failed at %d: got=%x expected=%x\n",
             i, unsigned_result[i], expected);
      ++num_failed;
      return;
    }
  }
}

static int8_t saturate_i8(int16_t value) {
  if (value > INT8_MAX) return INT8_MAX;
  if (value < INT8_MIN) return INT8_MIN;
  return (int8_t)value;
}

static void test_masked_triple_overlap_e8_m2_vl21(unsigned vstart) {
  const unsigned vl = 21;
  const unsigned vlmax = 256;

  for (unsigned i = 0; i < vlmax; ++i) {
    triple_overlap_initial[i] = (int8_t)(0x31u + 37u * i);
    triple_overlap_result[i] = 0;
  }
  for (unsigned i = 0; i < sizeof(mask_bits); ++i) mask_bits[i] = 0;
  for (unsigned i = 0; i < vl; ++i) {
    if ((i % 4) != 1) mask_bits[i / 8] |= (uint8_t)(1u << (i % 8));
  }

  asm volatile(
      "vsetvli zero, %[vlmax], e8, m2, tu, mu\n"
      "vle8.v v4, (%[initial])\n"
      "vsetvli zero, %[vl], e8, m2, tu, mu\n"
      "vlm.v v0, (%[mask])\n"
      "csrw vstart, %[vstart]\n"
      "csrwi vxrm, 2\n"
      "vnclip.wv v4, v4, v4, v0.t\n"
      "vsetvli zero, %[vlmax], e8, m2, tu, mu\n"
      "vse8.v v4, (%[result])\n"
      "fence rw, rw\n"
      :
      : [vlmax] "r"(vlmax), [vl] "r"(vl), [vstart] "r"(vstart),
        [initial] "r"(triple_overlap_initial), [mask] "r"(mask_bits),
        [result] "r"(triple_overlap_result)
      : "memory");

  for (unsigned i = 0; i < vlmax; ++i) {
    int8_t expected = triple_overlap_initial[i];
    if (i >= vstart && i < vl &&
        ((mask_bits[i / 8] >> (i % 8)) & 1u)) {
      uint16_t bits = (uint8_t)triple_overlap_initial[2 * i] |
                      ((uint16_t)(uint8_t)triple_overlap_initial[2 * i + 1] << 8);
      int16_t source = (int16_t)bits;
      unsigned shift = (uint8_t)triple_overlap_initial[i] & 0xfu;
      expected = saturate_i8((int16_t)(source >> shift));
    }
    if (triple_overlap_result[i] != expected) {
      printf("vnclip.wv masked triple overlap e8,m2,vl21,vstart%u failed at %d: "
             "got=%x expected=%x mask=%d\n", vstart,
             i, (uint8_t)triple_overlap_result[i], (uint8_t)expected,
             i < vl ? ((mask_bits[i / 8] >> (i % 8)) & 1u) : 0);
      ++num_failed;
      return;
    }
  }
}

static void test_masked_triple_overlap_vxsat(void) {
  const unsigned vl = 8;
  const unsigned vlmax = 256;
  unsigned long vxsat = 0;

  for (unsigned i = 0; i < vlmax; ++i) triple_overlap_initial[i] = 0;
  // Element 0 is enabled and computes zero. Element 1 is disabled but its
  // wide source is 0x7fff with shift zero, which would saturate to int8_t.
  triple_overlap_initial[2] = (int8_t)0xff;
  triple_overlap_initial[3] = (int8_t)0x7f;
  for (unsigned i = 0; i < sizeof(mask_bits); ++i) mask_bits[i] = 0;
  mask_bits[0] = 1;

  asm volatile(
      "vsetvli zero, %[vlmax], e8, m2, tu, mu\n"
      "vle8.v v4, (%[initial])\n"
      "vsetvli zero, %[vl], e8, m2, tu, mu\n"
      "vlm.v v0, (%[mask])\n"
      "csrwi vxrm, 2\n"
      "csrwi vxsat, 0\n"
      "vnclip.wv v4, v4, v4, v0.t\n"
      "csrr %[vxsat], vxsat\n"
      : [vxsat] "=r"(vxsat)
      : [vlmax] "r"(vlmax), [vl] "r"(vl),
        [initial] "r"(triple_overlap_initial), [mask] "r"(mask_bits)
      : "memory");

  if (vxsat != 0) {
    printf("vnclip.wv masked triple overlap incorrectly set vxsat=%lx\n", vxsat);
    ++num_failed;
  }
}

static void test_unsigned_masked_low_overlap_lmul4_vl25(void) {
  const unsigned vl = 25;

  initialize_data();
  for (unsigned i = 0; i < vl; ++i) unsigned_result[i] = 0;

  asm volatile(
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vle32.v v24, (%[source])\n"
      "vlm.v v0, (%[mask])\n"
      "csrwi vxrm, 2\n"
      "vnclipu.wi v24, v24, 8, v0.t\n"
      "vse16.v v24, (%[result])\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(vl), [source] "r"(unsigned_source),
        [mask] "r"(mask_bits), [result] "r"(unsigned_result)
      : "memory");

  for (unsigned i = 0; i < vl; ++i) {
    uint16_t expected;
    if ((mask_bits[i / 8] >> (i % 8)) & 1) {
      uint32_t shifted = unsigned_source[i] >> 8;
      expected = shifted > UINT16_MAX ? UINT16_MAX : (uint16_t)shifted;
    } else {
      uint32_t old_word = unsigned_source[i / 2];
      expected = (uint16_t)(old_word >> (16 * (i & 1)));
    }
    if (unsigned_result[i] != expected) {
      printf("vnclipu.wi masked low overlap e16,m4,vl25 failed at %d: "
             "got=%x expected=%x mask=%d\n",
             i, unsigned_result[i], expected,
             (mask_bits[i / 8] >> (i % 8)) & 1);
      ++num_failed;
      return;
    }
  }
}

static void test_signed_low_overlap_lmul4_vl79(void) {
  const unsigned vl = 79;

  for (unsigned i = 0; i < vl; ++i) {
    switch (i & 7) {
      case 0: signed_source[i] = (int32_t)(0x1200 + i); break;
      case 1: signed_source[i] = (int32_t)(0x10000 + i); break;
      case 2: signed_source[i] = -(int32_t)(0x10000 + i); break;
      case 3: signed_source[i] = 0; break;
      case 4: signed_source[i] = INT32_MAX; break;
      case 5: signed_source[i] = INT32_MIN; break;
      case 6: signed_source[i] = (int32_t)(0x7000 + i); break;
      default: signed_source[i] = -(int32_t)(0x7000 + i); break;
    }
    signed_result[i] = 0;
  }

  asm volatile(
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vle32.v v0, (%[source])\n"
      "csrwi vxrm, 2\n"
      "vnclip.wx v0, v0, zero\n"
      "vse16.v v0, (%[result])\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(vl), [source] "r"(signed_source),
        [result] "r"(signed_result)
      : "memory");

  for (unsigned i = 0; i < vl; ++i) {
    int16_t expected = saturate_i16(signed_source[i]);
    if (signed_result[i] != expected) {
      printf("vnclip.wx low overlap e16,m4,vl79 failed at %d: got=%x expected=%x\n",
             i, (uint16_t)signed_result[i], (uint16_t)expected);
      ++num_failed;
      return;
    }
  }
}

static void test_low_overlap_then_wide_source_lmul4_vl79(void) {
  const unsigned vl = 79;

  initialize_data();
  for (unsigned i = 0; i < vl; ++i) {
    uint32_t word = (uint32_t)signed_source[i];
    for (unsigned byte = 0; byte < sizeof(word); ++byte)
      overlap_bytes[i * sizeof(word) + byte] = (uint8_t)(word >> (8 * byte));
  }
  for (unsigned i = 0; i < vl; ++i) {
    uint16_t narrowed = (uint16_t)saturate_i16(signed_source[i]);
    overlap_bytes[2 * i] = (uint8_t)narrowed;
    overlap_bytes[2 * i + 1] = (uint8_t)(narrowed >> 8);
    signed_result[i] = 0;
  }

  asm volatile(
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vle32.v v0, (%[source])\n"
      "csrwi vxrm, 2\n"
      "vnclip.wx v0, v0, zero\n"
      "vnsra.wi v20, v0, 26\n"
      "vse16.v v20, (%[result])\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(vl), [source] "r"(signed_source),
        [result] "r"(signed_result)
      : "memory");

  for (unsigned i = 0; i < vl; ++i) {
    uint32_t word = 0;
    for (unsigned byte = 0; byte < sizeof(word); ++byte)
      word |= (uint32_t)overlap_bytes[i * sizeof(word) + byte] << (8 * byte);
    int16_t expected = (int16_t)((int32_t)word >> 26);
    if (signed_result[i] != expected) {
      printf("vnclip overlap then vnsra wide source e16,m4,vl79 failed at %d: "
             "got=%x expected=%x source=%x\n",
             i, (uint16_t)signed_result[i], (uint16_t)expected, word);
      ++num_failed;
      return;
    }
  }
}

static void test_low_overlap_source_reshuffle_lmul4_vl79(void) {
  const unsigned vl = 79;
  const unsigned source_vl = 2 * vl;

  initialize_data();
  for (unsigned i = 0; i < vl; ++i) {
    uint32_t word = (uint32_t)signed_source[i];
    overlap_source_e16[2 * i] = (uint16_t)word;
    overlap_source_e16[2 * i + 1] = (uint16_t)(word >> 16);
    signed_result[i] = 0;
  }

  asm volatile(
      "vsetvli zero, %[source_vl], e16, m8, tu, mu\n"
      "vle16.v v0, (%[source])\n"
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "csrwi vxrm, 2\n"
      "vnclip.wx v0, v0, zero\n"
      "vse16.v v0, (%[result])\n"
      "fence rw, rw\n"
      :
      : [source_vl] "r"(source_vl), [vl] "r"(vl),
        [source] "r"(overlap_source_e16), [result] "r"(signed_result)
      : "memory");

  for (unsigned i = 0; i < vl; ++i) {
    int16_t expected = saturate_i16(signed_source[i]);
    if (signed_result[i] != expected) {
      printf("vnclip low overlap source reshuffle e16,m4,vl79 failed at %d: "
             "got=%x expected=%x\n",
             i, (uint16_t)signed_result[i], (uint16_t)expected);
      ++num_failed;
      return;
    }
  }
}

static void test_signed_low_overlap_vstart_lmul4(void) {
  const unsigned vl = 79;
  const unsigned vstart = 13;
  const unsigned observed = MAX_ELEMENTS;

  initialize_data();
  for (unsigned i = 0; i < observed; ++i) signed_result[i] = 0;

  asm volatile(
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vle32.v v0, (%[source])\n"
      "csrw vstart, %[vstart]\n"
      "csrwi vxrm, 2\n"
      "vnclip.wx v0, v0, zero\n"
      "vsetvli zero, %[observed], e16, m4, tu, mu\n"
      "vse16.v v0, (%[result])\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(vl), [vstart] "r"(vstart), [observed] "r"(observed),
        [source] "r"(signed_source), [result] "r"(signed_result)
      : "memory");

  for (unsigned i = 0; i < observed; ++i) {
    uint32_t initial_word = (uint32_t)signed_source[i / 2];
    int16_t initial = (int16_t)(initial_word >> (16 * (i & 1)));
    int16_t expected = (i >= vstart && i < vl)
                           ? saturate_i16(signed_source[i])
                           : initial;
    if (signed_result[i] != expected) {
      printf("vnclip.wx low overlap vstart e16,m4 failed at %d: "
             "got=%x expected=%x region=%s\n",
             i, (uint16_t)signed_result[i], (uint16_t)expected,
             i < vstart ? "prestart" : (i < vl ? "active" : "tail"));
      ++num_failed;
      return;
    }
  }
}

static void test_signed_nonoverlap_vstart_lmul4(void) {
  const unsigned vl = 79;
  const unsigned vstart = 13;

  initialize_data();
  asm volatile(
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vle16.v v0, (%[background])\n"
      "vle32.v v8, (%[source])\n"
      "csrw vstart, %[vstart]\n"
      "csrwi vxrm, 2\n"
      "vnclip.wx v0, v8, zero\n"
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vse16.v v0, (%[result])\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(vl), [vstart] "r"(vstart), [source] "r"(signed_source),
        [background] "r"(background), [result] "r"(signed_result)
      : "memory");

  for (unsigned i = 0; i < vl; ++i) {
    int16_t expected = i < vstart ? background[i] : saturate_i16(signed_source[i]);
    if (signed_result[i] != expected) {
      printf("vnclip.wx nonoverlap vstart e16,m4 failed at %d: "
             "got=%x expected=%x region=%s\n",
             i, (uint16_t)signed_result[i], (uint16_t)expected,
             i < vstart ? "prestart" : "active");
      ++num_failed;
      return;
    }
  }
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  initialize_data();
  test_signed_masked_vl30();
  test_unsigned_unmasked_vl29();
  test_masked_triple_overlap_e8_m2_vl21(0);
  test_masked_triple_overlap_e8_m2_vl21(5);
  test_masked_triple_overlap_vxsat();
  test_unsigned_masked_low_overlap_lmul4_vl25();
  test_signed_low_overlap_lmul4_vl79();
  test_low_overlap_then_wide_source_lmul4_vl79();
  test_low_overlap_source_reshuffle_lmul4_vl79();
  test_signed_nonoverlap_vstart_lmul4();
  test_signed_low_overlap_vstart_lmul4();
  EXIT_CHECK();
}
