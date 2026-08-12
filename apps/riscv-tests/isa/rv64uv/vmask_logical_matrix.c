// Systematic mask-logical matrix across VL, LMUL, vstart, and policy encodings.

#include "vector_macros.h"

#define VLEN_BYTES 128
#define VLEN_WORDS (VLEN_BYTES / sizeof(uint64_t))

enum mask_op {
  OP_AND, OP_NAND, OP_ANDN, OP_OR, OP_NOR, OP_ORN, OP_XOR, OP_XNOR
};

static uint64_t source_a[VLEN_WORDS] __attribute__((aligned(128)));
static uint64_t source_b[VLEN_WORDS] __attribute__((aligned(128)));
static uint64_t initial_d[VLEN_WORDS] __attribute__((aligned(128)));
static uint64_t observed[VLEN_WORDS] __attribute__((aligned(128)));

static uint64_t low_bits(unsigned count) {
  if (count >= 64) return UINT64_MAX;
  return count == 0 ? 0 : (UINT64_C(1) << count) - 1;
}

static uint64_t mask_reference_word(enum mask_op op, uint64_t lhs, uint64_t rhs) {
  switch (op) {
    case OP_AND: return lhs & rhs;
    case OP_NAND: return ~(lhs & rhs);
    case OP_ANDN: return lhs & ~rhs;
    case OP_OR: return lhs | rhs;
    case OP_NOR: return ~(lhs | rhs);
    case OP_ORN: return lhs | ~rhs;
    case OP_XOR: return lhs ^ rhs;
    default: return ~(lhs ^ rhs);
  }
}

static void initialize_masks(void) {
  for (unsigned word = 0; word < VLEN_WORDS; ++word) {
    uint64_t lhs = 0;
    uint64_t rhs = 0;
    uint64_t initial = 0;
    for (unsigned byte = 0; byte < sizeof(uint64_t); ++byte) {
      unsigned index = word * sizeof(uint64_t) + byte;
      lhs |= (uint64_t)(uint8_t)(0x96u ^ (index * 37u)) << (byte * 8);
      rhs |= (uint64_t)(uint8_t)(0x69u ^ (index * 23u)) << (byte * 8);
      initial |= (uint64_t)(uint8_t)(0xa5u ^ (index * 11u)) << (byte * 8);
    }
    source_a[word] = lhs;
    source_b[word] = rhs;
    initial_d[word] = initial;
  }
}

static int check_mask(enum mask_op op, unsigned vl, unsigned vstart,
                      unsigned tail_undisturbed, unsigned observed_vstart) {
  if (observed_vstart != 0) {
    printf("mask matrix failed: vstart did not reset, got %d\n", observed_vstart);
    return 0;
  }
  for (unsigned word = 0; word < VLEN_WORDS; ++word) {
    unsigned base = word * 64;
    unsigned start_count = vstart <= base ? 0
                               : vstart >= base + 64 ? 64 : vstart - base;
    unsigned vl_count = vl <= base ? 0 : vl >= base + 64 ? 64 : vl - base;
    uint64_t prefix_mask = low_bits(start_count);
    uint64_t below_vl_mask = low_bits(vl_count);
    uint64_t active_mask = below_vl_mask & ~prefix_mask;
    uint64_t tail_mask = tail_undisturbed ? ~below_vl_mask : 0;
    uint64_t checked_bits = prefix_mask | active_mask | tail_mask;
    uint64_t computed = mask_reference_word(op, source_a[word], source_b[word]);
    uint64_t expected = (computed & active_mask) |
                        (initial_d[word] & (prefix_mask | tail_mask));
    uint64_t mismatch = (observed[word] ^ expected) & checked_bits;
    if (mismatch != 0) {
      unsigned bit_in_word = __builtin_ctzll(mismatch);
      unsigned bit = base + bit_in_word;
      printf("mask matrix failed: op=%d vl=%d vstart=%d bit=%d got=%d expected=%d\n",
             op, vl, vstart, bit, (unsigned)((observed[word] >> bit_in_word) & 1),
             (unsigned)((expected >> bit_in_word) & 1));
      return 0;
    }
  }
  return 1;
}

#define RUN_MASK(OPCODE, OP, VL, LMUL, VSTART, TAIL, MASK)               \
  do {                                                                    \
    unsigned observed_vstart;                                             \
    unsigned completion;                                                  \
    asm volatile(                                                         \
        "vl1re8.v v1, (%[lhs])\n"                                       \
        "vl1re8.v v2, (%[rhs])\n"                                       \
        "vl1re8.v v3, (%[initial])\n"                                   \
        "vsetvli zero, %[vl], e8, " #LMUL ", " #TAIL ", " #MASK "\n"  \
        "csrw vstart, %[start]\n"                                       \
        #OPCODE " v3, v1, v2\n"                                        \
        "csrr %[seen_start], vstart\n"                                  \
        "vs1r.v v3, (%[output])\n"                                      \
        "csrr %[done], vl\n"                                            \
        "fence rw, rw\n"                                                \
        : [seen_start] "=&r"(observed_vstart), [done] "=&r"(completion)  \
        : [lhs] "r"(source_a), [rhs] "r"(source_b),                      \
          [initial] "r"(initial_d), [output] "r"(observed),              \
          [vl] "r"((unsigned)(VL)), [start] "r"((unsigned)(VSTART))      \
        : "memory");                                                      \
    (void)completion;                                                     \
    if (!check_mask(OP, VL, VSTART, (#TAIL[1] == 'u'), observed_vstart))  \
      ++num_failed;                                                       \
  } while (0)

#define RUN_CONFIGS(OPCODE, OP)                                           \
  do {                                                                    \
    RUN_MASK(OPCODE, OP, 1, m1, 0, tu, mu);                              \
    RUN_MASK(OPCODE, OP, 7, m2, 1, ta, ma);                              \
    RUN_MASK(OPCODE, OP, 16, m4, 3, tu, ma);                             \
    RUN_MASK(OPCODE, OP, 31, m8, 7, ta, mu);                             \
    RUN_MASK(OPCODE, OP, 63, m1, 15, tu, mu);                            \
    RUN_MASK(OPCODE, OP, 96, m2, 32, ta, ma);                            \
    RUN_MASK(OPCODE, OP, 127, m4, 64, tu, ma);                           \
    RUN_MASK(OPCODE, OP, 255, m8, 128, ta, mu);                          \
  } while (0)

int main(void) {
  INIT_CHECK();
  enable_vec();
  initialize_masks();

  RUN_CONFIGS(vmand.mm, OP_AND);
  RUN_CONFIGS(vmnand.mm, OP_NAND);
  RUN_CONFIGS(vmandn.mm, OP_ANDN);
  RUN_CONFIGS(vmor.mm, OP_OR);
  RUN_CONFIGS(vmnor.mm, OP_NOR);
  RUN_CONFIGS(vmorn.mm, OP_ORN);
  RUN_CONFIGS(vmxor.mm, OP_XOR);
  RUN_CONFIGS(vmxnor.mm, OP_XNOR);

  EXIT_CHECK();
}
