// Multi-stage RVV workload for end-to-end datapath and memory validation.
#include <stdint.h>

#include "vector_macros.h"

#define INT_ELEMENTS 1025
#define INT_ROUNDS 8
#define MEM_ELEMENTS 257
#define FP_ELEMENTS 257
#define FP_MASK_BYTES ((FP_ELEMENTS + 7) / 8)

static uint32_t int_a[INT_ELEMENTS] __attribute__((aligned(128)));
static uint32_t int_b[INT_ELEMENTS] __attribute__((aligned(128)));
static uint32_t int_c[INT_ELEMENTS] __attribute__((aligned(128)));
static uint32_t int_out[INT_ELEMENTS] __attribute__((aligned(128)));
static uint16_t narrow_out[INT_ELEMENTS] __attribute__((aligned(128)));
static uint16_t roundtrip_out[INT_ELEMENTS] __attribute__((aligned(128)));

struct pair32 {
  uint32_t x;
  uint32_t y;
};

static struct pair32 segment_in[MEM_ELEMENTS] __attribute__((aligned(128)));
static struct pair32 segment_out[MEM_ELEMENTS] __attribute__((aligned(128)));
static uint16_t fp_a[FP_ELEMENTS] __attribute__((aligned(128)));
static uint16_t fp_b[FP_ELEMENTS] __attribute__((aligned(128)));
static uint8_t fp_masks[6][FP_MASK_BYTES] __attribute__((aligned(128)));
static unsigned reported_errors;

static void check_u32(const char *phase, unsigned index, uint32_t got,
                      uint32_t expected) {
  if (got == expected)
    return;
  if (reported_errors++ < 12)
    printf("RVV_COMPLEX_FAIL phase=%s index=%u got=%08x expected=%08x\n",
           phase, index, got, expected);
  ++num_failed;
}

static void check_u16(const char *phase, unsigned index, uint16_t got,
                      uint16_t expected) {
  if (got == expected)
    return;
  if (reported_errors++ < 12)
    printf("RVV_COMPLEX_FAIL phase=%s index=%u got=%04x expected=%04x\n",
           phase, index, got, expected);
  ++num_failed;
}

static uint32_t integer_expected(unsigned index) {
  uint32_t sum = int_a[index] + int_b[index];
  uint32_t product = sum * int_c[index];
  uint32_t mixed = product ^ int_a[index];
  uint32_t selected = int_b[index] < int_c[index] ? mixed : int_b[index];
  uint32_t difference = selected - int_a[index];
  return difference < int_c[index] ? difference : int_c[index];
}

static void test_integer_pipeline(void) {
  for (unsigned round = 0; round < INT_ROUNDS; ++round) {
    for (unsigned i = 0; i < INT_ELEMENTS; ++i) {
      int_a[i] = 0x9e3779b9u * (i + 1u) + round * 0x00010203u;
      int_b[i] = (i * 0x045d9f3bu) ^ (round * 0x00010001u + 0x0000f00du);
      int_c[i] = ((i + 3u) * 0x27d4eb2du) | 1u;
      int_out[i] = 0xdeadbeefu;
      narrow_out[i] = 0xa55au;
      roundtrip_out[i] = 0x5aa5u;
    }

    for (unsigned start = 0; start < INT_ELEMENTS;) {
      unsigned long remaining = INT_ELEMENTS - start;
      unsigned long actual_vl;
      unsigned long vector_sum;
      uint32_t expected_sum = 0;
      asm volatile(
          "vsetvli %[actual_vl], %[remaining], e32, m4, tu, mu\n"
          "vle32.v v8, (%[a])\n"
          "vle32.v v12, (%[b])\n"
          "vle32.v v16, (%[c])\n"
          "vmv.v.i v4, 0\n"
          "vadd.vv v20, v8, v12\n"
          "vmul.vv v20, v20, v16\n"
          "vxor.vv v20, v20, v8\n"
          "vmsltu.vv v0, v12, v16\n"
          "vmerge.vvm v24, v12, v20, v0\n"
          "vsub.vv v24, v24, v8\n"
          "vminu.vv v28, v24, v16\n"
          "vse32.v v28, (%[out])\n"
          "vredsum.vs v4, v28, v4\n"
          "vmv.x.s %[vector_sum], v4\n"
          "vsetvli zero, %[actual_vl], e16, m2, tu, mu\n"
          "vnsrl.wi v8, v28, 5\n"
          "vse16.v v8, (%[narrow])\n"
          "vle16.v v12, (%[narrow])\n"
          "vadd.vv v8, v8, v12\n"
          "vse16.v v8, (%[roundtrip])\n"
          : [actual_vl] "=&r"(actual_vl), [vector_sum] "=&r"(vector_sum)
          : [remaining] "r"(remaining), [a] "r"(&int_a[start]),
            [b] "r"(&int_b[start]), [c] "r"(&int_c[start]),
            [out] "r"(&int_out[start]), [narrow] "r"(&narrow_out[start]),
            [roundtrip] "r"(&roundtrip_out[start])
          : "memory");

      if (actual_vl == 0 || actual_vl > remaining) {
        printf("RVV_COMPLEX_FAIL phase=integer_vl start=%u vl=%lu remaining=%lu\n",
               start, actual_vl, remaining);
        ++num_failed;
        return;
      }
      for (unsigned lane = 0; lane < actual_vl; ++lane) {
        unsigned i = start + lane;
        uint32_t expected = integer_expected(i);
        uint16_t expected_narrow = (uint16_t)(expected >> 5);
        check_u32("integer_pipeline", i, int_out[i], expected);
        check_u16("narrow_roundtrip", i, roundtrip_out[i],
                  (uint16_t)(expected_narrow * 2u));
        expected_sum += expected;
      }
      check_u32("integer_reduction", start, (uint32_t)vector_sum,
                expected_sum);
      start += actual_vl;
    }
  }
  printf("RVV_COMPLEX_INTEGER_PASS rounds=%u elements_per_round=%u\n",
         INT_ROUNDS, INT_ELEMENTS);
}

static void test_segment_pipeline(void) {
  for (unsigned i = 0; i < MEM_ELEMENTS; ++i) {
    segment_in[i].x = 0x31415927u + i * 0x10203u;
    segment_in[i].y = 0x27182819u ^ (i * 0x01010101u);
    segment_out[i].x = 0xdeadbeefu;
    segment_out[i].y = 0xdeadbeefu;
  }

  for (unsigned start = 0; start < MEM_ELEMENTS;) {
    unsigned long remaining = MEM_ELEMENTS - start;
    unsigned long actual_vl;
    asm volatile(
        "vsetvli %[actual_vl], %[remaining], e32, m1, tu, mu\n"
        "vlseg2e32.v v8, (%[input])\n"
        "vadd.vv v8, v8, v9\n"
        "vxor.vi v9, v9, 13\n"
        "vsseg2e32.v v8, (%[output])\n"
        : [actual_vl] "=&r"(actual_vl)
        : [remaining] "r"(remaining), [input] "r"(&segment_in[start]),
          [output] "r"(&segment_out[start])
        : "memory");
    if (actual_vl == 0 || actual_vl > remaining) {
      printf("RVV_COMPLEX_FAIL phase=segment_vl start=%u vl=%lu remaining=%lu\n",
             start, actual_vl, remaining);
      ++num_failed;
      return;
    }
    for (unsigned lane = 0; lane < actual_vl; ++lane) {
      unsigned i = start + lane;
      check_u32("segment_add", i, segment_out[i].x,
                segment_in[i].x + segment_in[i].y);
      check_u32("segment_xor", i, segment_out[i].y,
                segment_in[i].y ^ 13u);
    }
    start += actual_vl;
  }
  printf("RVV_COMPLEX_SEGMENT_PASS elements=%u\n", MEM_ELEMENTS);
}

static void test_fp_compare_masks(void) {
  for (unsigned i = 0; i < FP_ELEMENTS; ++i) {
    fp_a[i] = (uint16_t)(0x3c00u + (i % 32u) * 0x20u);
    fp_b[i] = (uint16_t)(fp_a[i] + ((i % 3u) ? 0x20u : 0u));
  }
  for (unsigned op = 0; op < 6; ++op)
    for (unsigned byte = 0; byte < FP_MASK_BYTES; ++byte)
      fp_masks[op][byte] = 0;

  asm volatile("csrw fflags, zero" ::: "memory");
  // Run each comparison in a separate complete pass so each mask has an
  // independently checked packed representation.
  for (unsigned op = 0; op < 6; ++op) {
    for (unsigned start = 0; start < FP_ELEMENTS;) {
      unsigned long remaining = FP_ELEMENTS - start;
      unsigned long actual_vl;
      unsigned mask_offset = start >> 3;
      if (op == 0) {
        asm volatile("vsetvli %[vl], %[n], e16, m1, ta, ma\n"
                     "vle16.v v8, (%[a])\n vle16.v v12, (%[b])\n"
                     "vmfeq.vv v0, v8, v12\n vsm.v v0, (%[m])\n"
                     : [vl] "=&r"(actual_vl)
                     : [n] "r"(remaining), [a] "r"(&fp_a[start]),
                       [b] "r"(&fp_b[start]),
                       [m] "r"(&fp_masks[op][mask_offset])
                     : "memory");
      } else if (op == 1) {
        asm volatile("vsetvli %[vl], %[n], e16, m1, ta, ma\n"
                     "vle16.v v8, (%[a])\n vle16.v v12, (%[b])\n"
                     "vmfne.vv v0, v8, v12\n vsm.v v0, (%[m])\n"
                     : [vl] "=&r"(actual_vl)
                     : [n] "r"(remaining), [a] "r"(&fp_a[start]),
                       [b] "r"(&fp_b[start]),
                       [m] "r"(&fp_masks[op][mask_offset])
                     : "memory");
      } else if (op == 2) {
        asm volatile("vsetvli %[vl], %[n], e16, m1, ta, ma\n"
                     "vle16.v v8, (%[a])\n vle16.v v12, (%[b])\n"
                     "vmflt.vv v0, v8, v12\n vsm.v v0, (%[m])\n"
                     : [vl] "=&r"(actual_vl)
                     : [n] "r"(remaining), [a] "r"(&fp_a[start]),
                       [b] "r"(&fp_b[start]),
                       [m] "r"(&fp_masks[op][mask_offset])
                     : "memory");
      } else if (op == 3) {
        asm volatile("vsetvli %[vl], %[n], e16, m1, ta, ma\n"
                     "vle16.v v8, (%[a])\n vle16.v v12, (%[b])\n"
                     "vmfle.vv v0, v8, v12\n vsm.v v0, (%[m])\n"
                     : [vl] "=&r"(actual_vl)
                     : [n] "r"(remaining), [a] "r"(&fp_a[start]),
                       [b] "r"(&fp_b[start]),
                       [m] "r"(&fp_masks[op][mask_offset])
                     : "memory");
      } else if (op == 4) {
        asm volatile("vsetvli %[vl], %[n], e16, m1, ta, ma\n"
                     "vle16.v v8, (%[a])\n vle16.v v12, (%[b])\n"
                     "vmflt.vv v0, v12, v8\n vsm.v v0, (%[m])\n"
                     : [vl] "=&r"(actual_vl)
                     : [n] "r"(remaining), [a] "r"(&fp_a[start]),
                       [b] "r"(&fp_b[start]),
                       [m] "r"(&fp_masks[op][mask_offset])
                     : "memory");
      } else {
        asm volatile("vsetvli %[vl], %[n], e16, m1, ta, ma\n"
                     "vle16.v v8, (%[a])\n vle16.v v12, (%[b])\n"
                     "vmfle.vv v0, v12, v8\n vsm.v v0, (%[m])\n"
                     : [vl] "=&r"(actual_vl)
                     : [n] "r"(remaining), [a] "r"(&fp_a[start]),
                       [b] "r"(&fp_b[start]),
                       [m] "r"(&fp_masks[op][mask_offset])
                     : "memory");
      }
      if (actual_vl == 0 || actual_vl > remaining) {
        printf("RVV_COMPLEX_FAIL phase=fp_compare_vl op=%u start=%u vl=%lu\n",
               op, start, actual_vl);
        ++num_failed;
        return;
      }
      start += actual_vl;
    }
  }

  for (unsigned i = 0; i < FP_ELEMENTS; ++i) {
    unsigned relation[6] = {
        fp_a[i] == fp_b[i], fp_a[i] != fp_b[i], fp_a[i] < fp_b[i],
        fp_a[i] <= fp_b[i], fp_a[i] > fp_b[i], fp_a[i] >= fp_b[i]};
    for (unsigned op = 0; op < 6; ++op) {
      unsigned got = (fp_masks[op][i >> 3] >> (i & 7)) & 1u;
      if (got != relation[op]) {
        if (reported_errors++ < 12)
          printf("RVV_COMPLEX_FAIL phase=fp_compare op=%u index=%u got=%u expected=%u\n",
                 op, i, got, relation[op]);
        ++num_failed;
        break;
      }
    }
  }
  unsigned long flags;
  asm volatile("csrr %0, fflags" : "=r"(flags));
  if (flags != 0) {
    printf("RVV_COMPLEX_FAIL phase=fp_compare_flags got=%lu expected=0\n", flags);
    ++num_failed;
  }
  printf("RVV_COMPLEX_FP_PASS elements=%u comparisons=6\n", FP_ELEMENTS);
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  enable_fp();
  test_integer_pipeline();
  test_segment_pipeline();
  test_fp_compare_masks();
  if (num_failed == 0)
    printf("RVV_COMPLEX_PASS cases=3\n");
  EXIT_CHECK();
}
