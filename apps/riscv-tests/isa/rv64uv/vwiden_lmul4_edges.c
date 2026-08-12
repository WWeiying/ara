// Widening integer MAC element-order regressions at the largest legal LMUL.

#include "vector_macros.h"

#define VLMAX 256

static int16_t source_a[VLMAX] __attribute__((aligned(128)));
static int16_t source_b[VLMAX] __attribute__((aligned(128)));
static int32_t destination_seed[VLMAX] __attribute__((aligned(128)));
static int32_t result[VLMAX] __attribute__((aligned(128)));

static void initialize_data(void) {
  static const int16_t edge_values[] = {
      INT16_MIN, -30000, -16384, -1, 0, 1, 0x1403, 0x3fff, INT16_MAX,
  };
  const unsigned edge_count = sizeof(edge_values) / sizeof(edge_values[0]);

  for (unsigned index = 0; index < VLMAX; ++index) {
    source_a[index] = edge_values[(3 * index + 1) % edge_count];
    source_b[index] = edge_values[(5 * index + 6) % edge_count];
    destination_seed[index] = (int32_t)(UINT32_C(0x51000000) + 131u * index);
    result[index] = 0;
  }
}

static int32_t expected_value(unsigned index, unsigned vl) {
  if (index >= vl)
    return destination_seed[index];

  uint32_t product = (uint32_t)((int32_t)source_a[index] *
                                (int32_t)source_b[index]);
  return (int32_t)((uint32_t)destination_seed[index] + product);
}

static void test_vwmacc_vv_e16_m4(unsigned vl) {
  asm volatile(
      "vsetvli zero, %[vlmax], e32, m8, tu, mu\n"
      "vle32.v v16, (%[seed])\n"
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vle16.v v0, (%[source_a])\n"
      "vle16.v v8, (%[source_b])\n"
      "vwmacc.vv v16, v0, v8\n"
      "vsetvli zero, %[vlmax], e32, m8, tu, mu\n"
      "vse32.v v16, (%[result])\n"
      :
      : [vl] "r"(vl), [vlmax] "r"(VLMAX), [source_a] "r"(source_a),
        [source_b] "r"(source_b), [seed] "r"(destination_seed),
        [result] "r"(result)
      : "memory");

  MEMORY_BARRIER;
  unsigned mismatch_count = 0;
  for (unsigned index = 0; index < VLMAX; ++index) {
    int32_t expected = expected_value(index, vl);
    if (result[index] != expected) {
      if (mismatch_count < 8)
        printf("vwmacc.vv e16,m4 vl=%d failed at %d: got=%x expected=%x\n",
               vl, index, (uint32_t)result[index], (uint32_t)expected);
      ++mismatch_count;
    }
  }
  if (mismatch_count != 0) {
    printf("vwmacc.vv e16,m4 vl=%d mismatch count=%d\n", vl, mismatch_count);
    ++num_failed;
  }
}

int main(void) {
  static const unsigned vector_lengths[] = {
      1, 7, 8, 9, 31, 32, 33, 79, 127, 128, 129, 255,
  };

  INIT_CHECK();
  enable_vec();
  initialize_data();
  for (unsigned index = 0;
       index < sizeof(vector_lengths) / sizeof(vector_lengths[0]); ++index)
    test_vwmacc_vv_e16_m4(vector_lengths[index]);
  EXIT_CHECK();
}
