// Directed restart tests for whole-register loads and stores.

#include "vector_macros.h"

#define VREG_BYTES 128

static uint8_t source[VREG_BYTES] __attribute__((aligned(128)));
static uint8_t initial[VREG_BYTES] __attribute__((aligned(128)));
static uint8_t observed[VREG_BYTES] __attribute__((aligned(128)));
static uint8_t stored[VREG_BYTES] __attribute__((aligned(128)));

static void initialize_data(void) {
  for (unsigned i = 0; i < VREG_BYTES; ++i) {
    source[i] = (uint8_t)(0x31U + 37U * i);
    initial[i] = (uint8_t)(0xa5U ^ (11U * i));
    observed[i] = 0;
    stored[i] = 0x5a;
  }
}

static void wait_for_memory(void) {
  unsigned long vl;
  asm volatile("csrr %0, vl\n fence rw, rw" : "=r"(vl) :: "memory");
}

static void check_bytes(const char *name, const uint8_t *data,
                        unsigned preserved_bytes) {
  for (unsigned i = 0; i < VREG_BYTES; ++i) {
    uint8_t expected = i < preserved_bytes ? initial[i] : source[i];
    if (data[i] == expected)
      continue;
    printf("%s failed at %d: got=%x expected=%x\n", name, i, data[i],
           expected);
    ++num_failed;
    return;
  }
}

static void test_vl1re16_vstart(void) {
  unsigned long vstart = 3;
  asm volatile(
      "vsetivli zero, 1, e32, m1, tu, mu\n"
      "vl1re8.v v8, (%[initial])\n"
      "csrw vstart, %[vstart]\n"
      "vl1re16.v v8, (%[source])\n"
      "vs1r.v v8, (%[observed])\n"
      :
      : [initial] "r"(initial), [source] "r"(source),
        [observed] "r"(observed), [vstart] "r"(vstart)
      : "memory");
  wait_for_memory();
  check_bytes("vl1re16 vstart", observed, 6);
}

static void test_vl1re32_vstart(void) {
  unsigned long vstart = 2;
  asm volatile(
      "vl1re8.v v8, (%[initial])\n"
      "csrw vstart, %[vstart]\n"
      "vl1re32.v v8, (%[source])\n"
      "vs1r.v v8, (%[observed])\n"
      :
      : [initial] "r"(initial), [source] "r"(source),
        [observed] "r"(observed), [vstart] "r"(vstart)
      : "memory");
  wait_for_memory();
  check_bytes("vl1re32 vstart", observed, 8);
}

static void test_vl1re64_vstart(void) {
  unsigned long vstart = 1;
  asm volatile(
      "vl1re8.v v8, (%[initial])\n"
      "csrw vstart, %[vstart]\n"
      "vl1re64.v v8, (%[source])\n"
      "vs1r.v v8, (%[observed])\n"
      :
      : [initial] "r"(initial), [source] "r"(source),
        [observed] "r"(observed), [vstart] "r"(vstart)
      : "memory");
  wait_for_memory();
  check_bytes("vl1re64 vstart", observed, 8);
}

static void test_whole_load_empty_restart(void) {
  unsigned long vstart = VREG_BYTES / sizeof(uint32_t);
  asm volatile(
      "vl1re8.v v8, (%[initial])\n"
      "csrw vstart, %[vstart]\n"
      "vl1re32.v v8, (%[source])\n"
      "vs1r.v v8, (%[observed])\n"
      :
      : [initial] "r"(initial), [source] "r"(source),
        [observed] "r"(observed), [vstart] "r"(vstart)
      : "memory");
  wait_for_memory();
  check_bytes("vl1re32 empty restart", observed, VREG_BYTES);
}

static void test_whole_store_vstart(void) {
  unsigned long vstart = 9;
  for (unsigned i = 0; i < VREG_BYTES; ++i)
    stored[i] = initial[i];

  asm volatile(
      "vl1re8.v v12, (%[source])\n"
      "csrw vstart, %[vstart]\n"
      "vs1r.v v12, (%[stored])\n"
      :
      : [source] "r"(source), [stored] "r"(stored),
        [vstart] "r"(vstart)
      : "memory");
  wait_for_memory();
  check_bytes("vs1r vstart", stored, 9);
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  initialize_data();
  test_vl1re16_vstart();
  test_vl1re32_vstart();
  test_vl1re64_vstart();
  test_whole_load_empty_restart();
  test_whole_store_vstart();
  EXIT_CHECK();
}
