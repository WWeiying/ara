// Directed RVV 1.0 averaging matrix: 4 operations x 4 vxrm modes x 4 SEWs.

#include "vector_macros.h"

#define ELEMENTS 8

enum average_op { OP_VAADD, OP_VAADDU, OP_VASUB, OP_VASUBU };

static uint8_t lhs_bytes[64] __attribute__((aligned(128)));
static uint8_t rhs_bytes[64] __attribute__((aligned(128)));
static uint8_t result_bytes[64] __attribute__((aligned(128)));
static uint8_t expected_bytes[64] __attribute__((aligned(128)));

static uint64_t sew_mask(unsigned sew) {
  return sew == 64 ? UINT64_MAX : ((UINT64_C(1) << sew) - 1);
}

static void write_element(uint8_t *buffer, unsigned index, unsigned sew,
                          uint64_t value) {
  unsigned bytes = sew / 8;
  for (unsigned byte = 0; byte < bytes; ++byte)
    buffer[index * bytes + byte] = value >> (8 * byte);
}

static uint64_t read_element(const uint8_t *buffer, unsigned index,
                             unsigned sew) {
  uint64_t value = 0;
  unsigned bytes = sew / 8;
  for (unsigned byte = 0; byte < bytes; ++byte)
    value |= (uint64_t)buffer[index * bytes + byte] << (8 * byte);
  return value;
}

static __int128 sign_extend(uint64_t value, unsigned sew) {
  if (sew == 64)
    return (int64_t)value;
  uint64_t sign = UINT64_C(1) << (sew - 1);
  return (int64_t)((value ^ sign) - sign);
}

static unsigned average_increment(__uint128_t bits, unsigned vxrm) {
  unsigned rounding_bit = bits & 1;
  unsigned retained_lsb = (bits >> 1) & 1;
  switch (vxrm) {
    case 0: return rounding_bit;
    case 1: return rounding_bit & retained_lsb;
    case 2: return 0;
    default: return rounding_bit & !retained_lsb;
  }
}

static uint64_t average_reference(enum average_op op, uint64_t lhs,
                                  uint64_t rhs, unsigned sew, unsigned vxrm) {
  uint64_t mask = sew_mask(sew);
  if (op == OP_VAADD || op == OP_VASUB) {
    __int128 value = op == OP_VAADD
                         ? sign_extend(lhs, sew) + sign_extend(rhs, sew)
                         : sign_extend(lhs, sew) - sign_extend(rhs, sew);
    unsigned increment = average_increment((__uint128_t)value, vxrm);
    return (uint64_t)((value >> 1) + increment) & mask;
  }

  __uint128_t value;
  if (op == OP_VAADDU) {
    value = (__uint128_t)lhs + rhs;
  } else {
    __uint128_t wide_mask = (((__uint128_t)1 << (sew + 1)) - 1);
    value = ((__uint128_t)lhs - rhs) & wide_mask;
  }
  return (uint64_t)((value >> 1) + average_increment(value, vxrm)) & mask;
}

static void prepare_operands(unsigned sew) {
  static const uint64_t lhs[ELEMENTS] = {
      0, 1, UINT64_MAX, UINT64_C(0x8000000000000000),
      UINT64_C(0x7fffffffffffffff), 3, 6, UINT64_C(0xaaaaaaaaaaaaaaaa)};
  static const uint64_t rhs[ELEMENTS] = {
      1, UINT64_MAX, 1, 1, UINT64_C(0x8000000000000000),
      2, 3, UINT64_C(0x5555555555555555)};
  uint64_t mask = sew_mask(sew);
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    write_element(lhs_bytes, index, sew, lhs[index] & mask);
    write_element(rhs_bytes, index, sew, rhs[index] & mask);
  }
}

static int check_result(enum average_op op, unsigned sew, unsigned vxrm) {
  for (unsigned index = 0; index < ELEMENTS; ++index) {
    uint64_t lhs = read_element(lhs_bytes, index, sew);
    uint64_t rhs = read_element(rhs_bytes, index, sew);
    uint64_t expected = average_reference(op, lhs, rhs, sew, vxrm);
    uint64_t observed = read_element(result_bytes, index, sew);
    write_element(expected_bytes, index, sew, expected);
    if (observed != expected) {
      printf("average matrix failed: op=%d sew=%d vxrm=%d element=%d got=%lx expected=%lx\n",
             op, sew, vxrm, index, observed, expected);
      return 0;
    }
  }
  return 1;
}

#define RUN_AVERAGE(OPCODE, OP, SEW)                                      \
  do {                                                                    \
    prepare_operands(SEW);                                                \
    for (unsigned mode = 0; mode < 4; ++mode) {                           \
      set_vxrm(mode);                                                     \
      asm volatile(                                                       \
          "vsetvli zero, %[vl], e" #SEW ", m1, tu, mu\n"                \
          "vle" #SEW ".v v8, (%[lhs])\n"                                 \
          "vle" #SEW ".v v9, (%[rhs])\n"                                 \
          #OPCODE ".vv v10, v8, v9\n"                                    \
          "vse" #SEW ".v v10, (%[result])\n"                            \
          "csrr t0, vl\n"                                                \
          "fence rw, rw\n"                                               \
          :                                                               \
          : [vl] "r"(ELEMENTS), [lhs] "r"(lhs_bytes),                    \
            [rhs] "r"(rhs_bytes), [result] "r"(result_bytes)             \
          : "t0", "memory");                                             \
      if (!check_result(OP, SEW, mode))                                   \
        ++num_failed;                                                     \
    }                                                                     \
  } while (0)

int main(void) {
  INIT_CHECK();
  enable_vec();

  RUN_AVERAGE(vaadd, OP_VAADD, 8);
  RUN_AVERAGE(vaadd, OP_VAADD, 16);
  RUN_AVERAGE(vaadd, OP_VAADD, 32);
  RUN_AVERAGE(vaadd, OP_VAADD, 64);
  RUN_AVERAGE(vaaddu, OP_VAADDU, 8);
  RUN_AVERAGE(vaaddu, OP_VAADDU, 16);
  RUN_AVERAGE(vaaddu, OP_VAADDU, 32);
  RUN_AVERAGE(vaaddu, OP_VAADDU, 64);
  RUN_AVERAGE(vasub, OP_VASUB, 8);
  RUN_AVERAGE(vasub, OP_VASUB, 16);
  RUN_AVERAGE(vasub, OP_VASUB, 32);
  RUN_AVERAGE(vasub, OP_VASUB, 64);
  RUN_AVERAGE(vasubu, OP_VASUBU, 8);
  RUN_AVERAGE(vasubu, OP_VASUBU, 16);
  RUN_AVERAGE(vasubu, OP_VASUBU, 32);
  RUN_AVERAGE(vasubu, OP_VASUBU, 64);

  EXIT_CHECK();
}
