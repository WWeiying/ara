// Directed restart tests for unit-stride memory operations whose active tail
// crosses a VRF-word boundary while fitting in one AXI beat.

#include "vector_macros.h"

#define VL 38
#define VSTART 25
#define BASE_OFFSET 9
#define BUFFER_BYTES 80

static uint8_t source[BUFFER_BYTES] __attribute__((aligned(128)));
static uint8_t initial[VL] __attribute__((aligned(128)));
static uint8_t observed[VL] __attribute__((aligned(128)));
static uint8_t stored[BUFFER_BYTES] __attribute__((aligned(128)));

static void initialize_data(void) {
  for (unsigned i = 0; i < BUFFER_BYTES; ++i) {
    source[i] = (uint8_t)(0x31U + 17U * i);
    stored[i] = 0xa5U;
  }
  for (unsigned i = 0; i < VL; ++i) {
    initial[i] = (uint8_t)(0xc3U ^ (13U * i));
    observed[i] = 0;
  }
}

static void wait_for_memory(void) {
  unsigned long vl;
  asm volatile("csrr %0, vl\n fence rw, rw" : "=r"(vl) :: "memory");
}

static void test_unit_load_vstart(void) {
  asm volatile(
      "vsetvli zero, %[vl], e8, m1, tu, mu\n"
      "vle8.v v8, (%[initial])\n"
      "csrw vstart, %[vstart]\n"
      "vle8.v v8, (%[source])\n"
      "vse8.v v8, (%[observed])\n"
      :
      : [vl] "r"(VL), [vstart] "r"(VSTART), [initial] "r"(initial),
        [source] "r"(&source[BASE_OFFSET]), [observed] "r"(observed)
      : "memory");
  wait_for_memory();

  for (unsigned i = 0; i < VL; ++i) {
    uint8_t expected = i < VSTART ? initial[i] : source[BASE_OFFSET + i];
    if (observed[i] == expected)
      continue;
    printf("unit load vstart failed at %d: got=%x expected=%x\n", i,
           observed[i], expected);
    ++num_failed;
    return;
  }
}

static void test_unit_store_vstart(void) {
  asm volatile(
      "vsetvli zero, %[vl], e8, m1, tu, mu\n"
      "vle8.v v12, (%[source])\n"
      "csrw vstart, %[vstart]\n"
      "vse8.v v12, (%[stored])\n"
      :
      : [vl] "r"(VL), [vstart] "r"(VSTART), [source] "r"(source),
        [stored] "r"(&stored[BASE_OFFSET])
      : "memory");
  wait_for_memory();

  for (unsigned i = 0; i < BUFFER_BYTES; ++i) {
    uint8_t expected = 0xa5U;
    if (i >= BASE_OFFSET + VSTART && i < BASE_OFFSET + VL)
      expected = source[i - BASE_OFFSET];
    if (stored[i] == expected)
      continue;
    printf("unit store vstart failed at %d: got=%x expected=%x\n", i,
           stored[i], expected);
    ++num_failed;
    return;
  }
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  initialize_data();
  test_unit_load_vstart();
  test_unit_store_vstart();
  EXIT_CHECK();
}
