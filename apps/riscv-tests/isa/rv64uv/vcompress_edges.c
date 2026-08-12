// Directed VCOMPRESS regressions for empty selections and trailing mask zeros.

#include "vector_macros.h"

#define ELEMENTS 15

static uint32_t source[ELEMENTS] __attribute__((aligned(128))) = {
    0x100, 0x101, 0x102, 0x103, 0x104,
    0x105, 0x106, 0x107, 0x108, 0x109,
    0x10a, 0x10b, 0x10c, 0x10d, 0x10e};

static uint32_t background[ELEMENTS] __attribute__((aligned(128))) = {
    0xa00, 0xa01, 0xa02, 0xa03, 0xa04,
    0xa05, 0xa06, 0xa07, 0xa08, 0xa09,
    0xa0a, 0xa0b, 0xa0c, 0xa0d, 0xa0e};

static uint32_t result[ELEMENTS] __attribute__((aligned(128)));

static const uint8_t mask_none[2] __attribute__((aligned(128))) = {0x00, 0x00};
static const uint8_t mask_one_then_zeros[2] __attribute__((aligned(128))) = {0x08, 0x00};
static const uint8_t mask_last[2] __attribute__((aligned(128))) = {0x00, 0x40};
static const uint8_t mask_mixed_then_zeros[2] __attribute__((aligned(128))) = {0x85, 0x01};
static const uint8_t mask_a[2] __attribute__((aligned(128))) = {0x39, 0x25};
static const uint8_t mask_b[2] __attribute__((aligned(128))) = {0x46, 0x12};
static const uint8_t mask_old[2] __attribute__((aligned(128))) = {0xa5, 0x5a};
static uint8_t mask_result[2] __attribute__((aligned(128)));

#define CROSS_ELEMENTS 128
#define CROSS_SELECTED 80

static uint16_t cross_source[CROSS_ELEMENTS] __attribute__((aligned(128)));
static uint16_t cross_background[CROSS_ELEMENTS] __attribute__((aligned(128)));
static uint16_t cross_result[CROSS_ELEMENTS] __attribute__((aligned(128)));
static uint8_t cross_mask[CROSS_ELEMENTS / 8] __attribute__((aligned(128)));

static void run_compress(const uint8_t *mask) {
  asm volatile(
      "vsetvli zero, %[vl], e32, mf2, tu, mu\n"
      "vle32.v v8, (%[source])\n"
      "vle32.v v10, (%[background])\n"
      "vlm.v v0, (%[mask])\n"
      "vcompress.vm v10, v8, v0\n"
      "vse32.v v10, (%[result])\n"
      "csrr zero, vl\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(ELEMENTS), [source] "r"(source),
        [background] "r"(background), [mask] "r"(mask), [result] "r"(result)
      : "memory");
}

static void check_maskb_release(void) {
  asm volatile(
      "vsetvli zero, %[vl], e32, mf2, tu, mu\n"
      "vle32.v v8, (%[source])\n"
      "vle32.v v10, (%[background])\n"
      "vlm.v v0, (%[none])\n"
      "vlm.v v20, (%[mask_a])\n"
      "vlm.v v7, (%[mask_b])\n"
      "vlm.v v22, (%[mask_old])\n"
      "vcompress.vm v10, v8, v0\n"
      "vmor.mm v22, v20, v7\n"
      "vsm.v v22, (%[result])\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(ELEMENTS), [source] "r"(source),
        [background] "r"(background), [none] "r"(mask_none),
        [mask_a] "r"(mask_a), [mask_b] "r"(mask_b),
        [mask_old] "r"(mask_old), [result] "r"(mask_result)
      : "memory");

  for (unsigned bit = 0; bit < ELEMENTS; ++bit) {
    unsigned got = (mask_result[bit / 8] >> (bit % 8)) & 1;
    unsigned expected = ((mask_a[bit / 8] | mask_b[bit / 8]) >> (bit % 8)) & 1;
    if (got != expected) {
      printf("VCOMPRESS MaskB release failed at bit %d: got=%d expected=%d\n",
             bit, got, expected);
      ++num_failed;
      return;
    }
  }
}

static void check_cross_eew_tail_preservation(void) {
  for (unsigned index = 0; index < CROSS_ELEMENTS; ++index) {
    cross_source[index] = 0x1000 + index;
    cross_background[index] = 0x6000 + index;
    cross_result[index] = 0;
  }
  for (unsigned byte = 0; byte < sizeof(cross_mask); ++byte)
    cross_mask[byte] = byte < CROSS_SELECTED / 8 ? 0xff : 0x00;

  asm volatile(
      "vsetvli zero, %[bg_vl], e64, m2, tu, mu\n"
      "vle64.v v24, (%[background])\n"
      "vsetvli zero, %[vl], e16, m2, tu, mu\n"
      "vle16.v v8, (%[source])\n"
      "vlm.v v0, (%[mask])\n"
      "vcompress.vm v24, v8, v0\n"
      "vse16.v v24, (%[result])\n"
      "fence rw, rw\n"
      :
      : [bg_vl] "r"(CROSS_ELEMENTS / 4), [vl] "r"(CROSS_ELEMENTS),
        [source] "r"(cross_source), [background] "r"(cross_background),
        [mask] "r"(cross_mask), [result] "r"(cross_result)
      : "memory");

  for (unsigned index = 0; index < CROSS_ELEMENTS; ++index) {
    uint16_t expected = index < CROSS_SELECTED
                      ? cross_source[index]
                      : cross_background[index];
    if (cross_result[index] != expected) {
      printf("VCOMPRESS cross-EEW tail failed at %d: got=%x expected=%x\n",
             index, cross_result[index], expected);
      ++num_failed;
      return;
    }
  }
}

static void check_result(unsigned case_number, const unsigned *selected,
                         unsigned selected_count) {
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    uint32_t expected = index < selected_count
                      ? source[selected[index]]
                      : background[index];
    if (result[index] != expected) {
      printf("VCOMPRESS case %d failed at %d: got=%x expected=%x\n",
             case_number, index, result[index], expected);
      ++num_failed;
      return;
    }
  }
}

int main(void) {
  static const unsigned one_then_zeros[] = {3};
  static const unsigned last[] = {14};
  static const unsigned mixed_then_zeros[] = {0, 2, 7, 8};

  INIT_CHECK();
  enable_vec();

  run_compress(mask_none);
  check_result(1, 0, 0);

  run_compress(mask_one_then_zeros);
  check_result(2, one_then_zeros, 1);

  run_compress(mask_last);
  check_result(3, last, 1);

  run_compress(mask_mixed_then_zeros);
  check_result(4, mixed_then_zeros, 4);

  check_maskb_release();
  check_cross_eew_tail_preservation();

  EXIT_CHECK();
}
