// Directed mask-memory checks for fixed EMUL=1 and byte-granular vstart.

#include "vector_macros.h"

static uint8_t source[16] __attribute__((aligned(128))) = {
    0x12, 0x34, 0x56, 0x78, 0x9a, 0xbc, 0xde, 0xf0,
    0x5a, 0x55, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc};
static uint8_t target[16] __attribute__((aligned(128)));
static uint8_t no_op_target[16] __attribute__((aligned(128)));

static void check_byte(unsigned id, uint8_t observed, uint8_t expected) {
  if (observed != expected) {
    printf("Index %d FAILED. Got %x, expected %x.\n", id, observed, expected);
    ++num_failed;
  }
}

static void check_no_op_preserves_source(void) {
  unsigned long fill_vl = 32;
  unsigned long vl = 79;
  unsigned long start = 49;
  unsigned long pattern = 0x1ff;
  unsigned long popcount;

  // A no-op mask store must not alter its source register, even when that
  // register is currently encoded with a different EEW from the store.
  asm volatile(
      "vsetvli zero, %[fill_vl], e32, m1, tu, mu\n"
      "vmv.v.i v19, 0\n"
      "vmv.s.x v19, %[pattern]\n"
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "csrw vstart, %[start]\n"
      "vsm.v v19, (%[target])\n"
      "vcpop.m %[popcount], v19\n"
      : [popcount] "=r"(popcount)
      : [fill_vl] "r"(fill_vl), [vl] "r"(vl), [start] "r"(start),
        [pattern] "r"(pattern), [target] "r"(no_op_target)
      : "memory");

  if (popcount != 9) {
    printf("no-op vsm source FAILED. Got %ld, expected 9.\n", popcount);
    ++num_failed;
  }
}

int main(void) {
  INIT_CHECK();
  enable_vec();

  for (unsigned i = 0; i < 16; ++i) {
    target[i] = 0xa5;
    no_op_target[i] = 0x3c;
  }

  // With e16,m4 and vl=79, mask memory operations still use one register.
  // v19 is deliberately not aligned as an LMUL=2 or LMUL=4 data group.
  unsigned long vl = 79;
  asm volatile(
      "vsetvli zero, %[vl], e16, m4, tu, mu\n"
      "vlm.v v19, (%[source])\n"
      "vsm.v v19, (%[target])\n"
      :
      : [vl] "r"(vl), [source] "r"(source), [target] "r"(target)
      : "memory");
  asm volatile("fence rw, rw" ::: "memory");

  for (unsigned i = 0; i < 9; ++i)
    check_byte(i, target[i], source[i]);
  // Bit 79 is a mask tail bit and may be agnostic after vlm.v.
  check_byte(9, target[9] & 0x7f, source[9] & 0x7f);
  for (unsigned i = 10; i < 16; ++i)
    check_byte(i, target[i], 0xa5);

  // Mask-memory vstart is byte-granular. evl=ceil(79/8)=10, so byte 49
  // is past evl: the instruction performs no accesses and clears vstart.
  unsigned long start = 49;
  unsigned long vstart_after;
  asm volatile(
      "csrw vstart, %[start]\n"
      "vsm.v v19, (%[target])\n"
      "csrr %[after], vstart\n"
      : [after] "=r"(vstart_after)
      : [start] "r"(start), [target] "r"(no_op_target)
      : "memory");
  asm volatile("fence rw, rw" ::: "memory");

  if (vstart_after != 0) {
    printf("vstart FAILED. Got %lx, expected 0.\n", vstart_after);
    ++num_failed;
  }
  for (unsigned i = 0; i < 16; ++i)
    check_byte(16 + i, no_op_target[i], 0x3c);

  check_no_op_preserves_source();

  EXIT_CHECK();
}
