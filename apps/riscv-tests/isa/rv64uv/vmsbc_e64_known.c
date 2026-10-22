#include "vector_macros.h"

#define VL 6
#define VLEN_BYTES (VLEN / 8)

static uint64_t source[VL] __attribute__((aligned(128)));
static uint64_t operand[VL] __attribute__((aligned(128)));
static uint8_t initial[VLEN_BYTES] __attribute__((aligned(128)));
static uint8_t borrow[VLEN_BYTES] __attribute__((aligned(128)));
static uint8_t observed[VLEN_BYTES] __attribute__((aligned(128)));

int main(void) {
  INIT_CHECK();
  enable_vec();

  for (unsigned i = 0; i < VL; ++i) {
    source[i] = i + 4;
    operand[i] = i;
  }
  source[0] = 3;
  operand[0] = UINT64_MAX - 17;
  for (unsigned i = 0; i < VLEN_BYTES; ++i) {
    initial[i] = 0xa5;
    borrow[i] = 0;
  }
  borrow[0] = 1;

  asm volatile(
      "vl1re8.v v27, (%[initial])\n"
      "vl1re8.v v0, (%[borrow])\n"
      "vsetvli zero, %[vl], e64, m1, tu, mu\n"
      "vle64.v v8, (%[source])\n"
      "vle64.v v7, (%[operand])\n"
      "vmsbc.vvm v27, v8, v7, v0\n"
      "vs1r.v v27, (%[observed])\n"
      "fence rw, rw\n"
      :
      : [initial] "r"(initial), [borrow] "r"(borrow), [vl] "r"(VL),
        [source] "r"(source), [operand] "r"(operand), [observed] "r"(observed)
      : "memory");

  for (unsigned bit = 0; bit < VLEN; ++bit) {
    unsigned expected = bit < VL ? (bit == 0) : ((initial[bit / 8] >> (bit % 8)) & 1);
    unsigned actual = (observed[bit / 8] >> (bit % 8)) & 1;
    if (actual != expected) {
      printf("vmsbc e64 bit %u: got %u, expected %u\n", bit, actual, expected);
      ++num_failed;
      break;
    }
  }

  EXIT_CHECK();
}
