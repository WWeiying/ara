// VMADC/VMSBC mask destinations must consume v0 carry-in and preserve TU tails.

#include "vector_macros.h"

#define VLEN_BITS VLEN
#define VLEN_BYTES (VLEN_BITS / 8)
#define VL 15
#define SCALAR_OPERAND 1u

enum operation_kind { ADD_CARRY, SUB_BORROW };
enum operand_kind { SCALAR_FORM, VECTOR_FORM };

static uint32_t source[VL] __attribute__((aligned(128)));
static uint32_t vector_operand[VL] __attribute__((aligned(128)));
static uint8_t carry_mask[VLEN_BYTES] __attribute__((aligned(128)));
static uint8_t initial_mask[VLEN_BYTES] __attribute__((aligned(128)));
static uint8_t observed_mask[VLEN_BYTES] __attribute__((aligned(128)));

static unsigned bit_at(const uint8_t *buffer, unsigned bit) {
  return (buffer[bit >> 3] >> (bit & 7)) & 1u;
}

static void initialize_data(void) {
  for (unsigned index = 0; index < VL; ++index) {
    switch (index & 3u) {
      case 0:
        source[index] = UINT32_MAX;
        vector_operand[index] = 0;
        break;
      case 1:
        source[index] = UINT32_MAX - 1u;
        vector_operand[index] = 1;
        break;
      case 2:
        source[index] = index;
        vector_operand[index] = UINT32_MAX;
        break;
      default:
        source[index] = index;
        vector_operand[index] = index + 1u;
        break;
    }
  }

  for (unsigned index = 0; index < VLEN_BYTES; ++index) {
    carry_mask[index] = (uint8_t)(0x6du ^ (29u * index));
    initial_mask[index] = (uint8_t)(0xa5u ^ (17u * index));
  }
}

static unsigned expected_active_bit(unsigned bit, enum operation_kind operation,
                                    enum operand_kind operand) {
  uint64_t rhs = operand == SCALAR_FORM ? SCALAR_OPERAND : vector_operand[bit];
  uint64_t carry_or_borrow = bit_at(carry_mask, bit);

  if (operation == ADD_CARRY)
    return ((uint64_t)source[bit] + rhs + carry_or_borrow) >> 32;
  return (uint64_t)source[bit] < rhs + carry_or_borrow;
}

static void check_result(const char *name, unsigned vstart,
                         enum operation_kind operation,
                         enum operand_kind operand, unsigned long observed_vstart) {
  if (observed_vstart != 0) {
    printf("%s did not clear vstart: got=%ld\n", name, observed_vstart);
    ++num_failed;
  }

  for (unsigned bit = 0; bit < VLEN_BITS; ++bit) {
    unsigned expected =
        (bit < vstart || bit >= VL)
            ? bit_at(initial_mask, bit)
            : expected_active_bit(bit, operation, operand);
    if (bit_at(observed_mask, bit) != expected) {
      printf("%s failed: vstart=%d bit=%d got=%d expected=%d\n", name, vstart,
             bit, bit_at(observed_mask, bit), expected);
      ++num_failed;
      break;
    }
  }
}

static void run_vmadc_vxm(unsigned vstart) {
  unsigned long observed_vstart;
  unsigned long scalar = SCALAR_OPERAND;
  asm volatile(
      "vl1re8.v v27, (%[initial])\n"
      "vl1re8.v v0, (%[carry])\n"
      "vsetvli zero, %[vl], e32, mf2, tu, mu\n"
      "vle32.v v29, (%[source])\n"
      "csrw vstart, %[start]\n"
      "vmadc.vxm v27, v29, %[scalar], v0\n"
      "csrr %[seen_start], vstart\n"
      "vs1r.v v27, (%[observed])\n"
      "fence rw, rw\n"
      : [seen_start] "=&r"(observed_vstart)
      : [initial] "r"(initial_mask), [carry] "r"(carry_mask),
        [source] "r"(source), [vl] "r"(VL), [start] "r"(vstart),
        [scalar] "r"(scalar), [observed] "r"(observed_mask)
      : "memory");
  check_result("vmadc.vxm", vstart, ADD_CARRY, SCALAR_FORM, observed_vstart);
}

static void run_vmadc_vvm(unsigned vstart) {
  unsigned long observed_vstart;
  asm volatile(
      "vl1re8.v v27, (%[initial])\n"
      "vl1re8.v v0, (%[carry])\n"
      "vsetvli zero, %[vl], e32, mf2, tu, mu\n"
      "vle32.v v29, (%[source])\n"
      "vle32.v v8, (%[operand])\n"
      "csrw vstart, %[start]\n"
      "vmadc.vvm v27, v29, v8, v0\n"
      "csrr %[seen_start], vstart\n"
      "vs1r.v v27, (%[observed])\n"
      "fence rw, rw\n"
      : [seen_start] "=&r"(observed_vstart)
      : [initial] "r"(initial_mask), [carry] "r"(carry_mask),
        [source] "r"(source), [operand] "r"(vector_operand), [vl] "r"(VL),
        [start] "r"(vstart), [observed] "r"(observed_mask)
      : "memory");
  check_result("vmadc.vvm", vstart, ADD_CARRY, VECTOR_FORM, observed_vstart);
}

static void run_vmsbc_vxm(unsigned vstart) {
  unsigned long observed_vstart;
  unsigned long scalar = SCALAR_OPERAND;
  asm volatile(
      "vl1re8.v v27, (%[initial])\n"
      "vl1re8.v v0, (%[carry])\n"
      "vsetvli zero, %[vl], e32, mf2, tu, mu\n"
      "vle32.v v29, (%[source])\n"
      "csrw vstart, %[start]\n"
      "vmsbc.vxm v27, v29, %[scalar], v0\n"
      "csrr %[seen_start], vstart\n"
      "vs1r.v v27, (%[observed])\n"
      "fence rw, rw\n"
      : [seen_start] "=&r"(observed_vstart)
      : [initial] "r"(initial_mask), [carry] "r"(carry_mask),
        [source] "r"(source), [vl] "r"(VL), [start] "r"(vstart),
        [scalar] "r"(scalar), [observed] "r"(observed_mask)
      : "memory");
  check_result("vmsbc.vxm", vstart, SUB_BORROW, SCALAR_FORM, observed_vstart);
}

static void run_vmsbc_vvm(unsigned vstart) {
  unsigned long observed_vstart;
  asm volatile(
      "vl1re8.v v27, (%[initial])\n"
      "vl1re8.v v0, (%[carry])\n"
      "vsetvli zero, %[vl], e32, mf2, tu, mu\n"
      "vle32.v v29, (%[source])\n"
      "vle32.v v8, (%[operand])\n"
      "csrw vstart, %[start]\n"
      "vmsbc.vvm v27, v29, v8, v0\n"
      "csrr %[seen_start], vstart\n"
      "vs1r.v v27, (%[observed])\n"
      "fence rw, rw\n"
      : [seen_start] "=&r"(observed_vstart)
      : [initial] "r"(initial_mask), [carry] "r"(carry_mask),
        [source] "r"(source), [operand] "r"(vector_operand), [vl] "r"(VL),
        [start] "r"(vstart), [observed] "r"(observed_mask)
      : "memory");
  check_result("vmsbc.vvm", vstart, SUB_BORROW, VECTOR_FORM, observed_vstart);
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  initialize_data();

  run_vmadc_vxm(0);
  run_vmadc_vvm(0);
  run_vmsbc_vxm(0);
  run_vmsbc_vvm(0);

  EXIT_CHECK();
}
