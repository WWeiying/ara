// SPDX-License-Identifier: SHL-0.51
// Original control-cross encodings must trap at e64, then execute at e32.
#include "vector_macros.h"

static volatile uint64_t trap_count, trap_cause, trap_pc, trap_tval;
static uint64_t initial[16] __attribute__((aligned(128)));
static uint64_t result[16] __attribute__((aligned(128)));
static uint32_t source[2] __attribute__((aligned(128)));
static uint64_t seed __attribute__((aligned(128)));

// Preserve all interrupted registers, including the inline asm's live inputs.
void __attribute__((naked, used, aligned(4))) mtvec_handler(void) {
  asm volatile(
      "addi sp, sp, -16\n sd t0, 0(sp)\n sd t1, 8(sp)\n"
      "csrr t0, mcause\n la t1, trap_cause\n sd t0, 0(t1)\n"
      "csrr t0, mepc\n la t1, trap_pc\n sd t0, 0(t1)\n"
      "csrr t0, mtval\n la t1, trap_tval\n sd t0, 0(t1)\n"
      "la t1, trap_count\n ld t0, 0(t1)\n addi t0, t0, 1\n sd t0, 0(t1)\n"
      "csrr t0, mepc\n addi t0, t0, 4\n csrw mepc, t0\n"
      "ld t0, 0(sp)\n ld t1, 8(sp)\n addi sp, sp, 16\n mret\n");
}

void rvtest_init(void) {
  asm volatile("csrw mtvec, %0" :: "r"(mtvec_handler) : "memory");
}

static void check(unsigned id, unsigned legal, unsigned reduction,
                  uint64_t expected, uint64_t flags, uint64_t restart) {
  for (unsigned i = 0; i < 16; ++i) {
    uint64_t want = legal && (i == 0 || (!reduction && i == 1))
                        ? expected : initial[i];
    if (result[i] != want) {
      printf("FAIL width id=%u legal=%u i=%u got=%lx expected=%lx\n",
             id, legal, i, result[i], want);
      ++num_failed;
    }
  }
  if (flags != 8 || restart != 0) {
    printf("FAIL width id=%u legal=%u flags=%lx vstart=%lu\n",
           id, legal, flags, restart);
    ++num_failed;
  }
}

#define SEED_LOAD(REG)                                                        \
  "vsetivli zero, 1, e64, m1, tu, mu\n vle64.v " REG ", (%[seed])\n"

#define RUN_CASE(ID, WORD, VD, VS, LMUL, VL, RED, SEED_SETUP, GOLD)             \
  do {                                                                        \
    unsigned long pc, flags, restart, before = trap_count;                     \
    asm volatile(                                                            \
        "vsetivli zero, 16, e64, m1, tu, mu\n"                               \
        "vle64.v " VD ", (%[initial])\n"                                    \
        "vsetivli zero, 16, e8, m1, tu, mu\n vmv.v.i v0, -1\n"              \
        "vsetvli zero, %[vl], e64, " LMUL ", tu, mu\n"                      \
        "csrwi frm, 0\n csrwi fflags, 8\n"                                  \
        "la %[pc], 1f\n 1: .word " #WORD "\n"                              \
        "csrr %[flags], fflags\n csrr %[restart], vstart\n"                  \
        "vsetivli zero, 16, e64, m1, tu, mu\n"                               \
        "vse64.v " VD ", (%[result])\n fence\n csrr zero, vl\n"             \
        : [pc] "=&r"(pc), [flags] "=&r"(flags), [restart] "=&r"(restart)      \
        : [initial] "r"(initial), [result] "r"(result), [vl] "r"(VL)          \
        : "memory", "v0", "v8", "v16", "v17", "v18", "v19", "v20", "v21", \
          "v22", "v23", "v24", "v25", "v26", "v27", "v28", "v29", "v30", "v31"); \
    if (trap_count != before + 1 || trap_cause != 2 || trap_pc != pc ||        \
        trap_tval != WORD) {                                                  \
      printf("FAIL width id=%u traps=%lu cause=%lu pc=%lx expected_pc=%lx "     \
             "tval=%lx\n", ID, trap_count - before, trap_cause, trap_pc, pc,   \
             trap_tval);                                                      \
      ++num_failed;                                                           \
    }                                                                         \
    check(ID, 0, RED, GOLD, flags, restart);                                    \
    before = trap_count;                                                       \
    asm volatile(                                                             \
        SEED_SETUP                                                            \
        "vsetivli zero, 2, e32, m1, tu, mu\n"                                \
        "vle32.v " VS ", (%[source])\n"                                     \
        "vsetivli zero, 2, e32, " LMUL ", tu, mu\n"                         \
        ".word " #WORD "\n"                                                  \
        "csrr %[flags], fflags\n csrr %[restart], vstart\n"                  \
        "vsetivli zero, 16, e64, m1, tu, mu\n"                               \
        "vse64.v " VD ", (%[result])\n fence\n csrr zero, vl\n"             \
        : [flags] "=&r"(flags), [restart] "=&r"(restart)                       \
        : [source] "r"(source), [seed] "r"(&seed), [result] "r"(result)        \
        : "memory", "v4", "v8", "v16", "v17", "v18", "v19", "v20", "v21", \
          "v22", "v23", "v24", "v25", "v26", "v27", "v28", "v29", "v30", "v31"); \
    if (trap_count != before) {                                                \
      printf("FAIL width id=%u legal e32 trapped cause=%lu\n", ID, trap_cause); \
      ++num_failed;                                                           \
    }                                                                         \
    check(ID, 1, RED, GOLD, flags, restart);                                    \
  } while (0)

int main(void) {
  INIT_CHECK();
  enable_vec();
  enable_fp();
#ifdef __SPIKE__
  // The Spike benchmark runtime starts main in M-mode, without rvtest_init.
  rvtest_init();
#endif
  trap_count = trap_cause = trap_pc = trap_tval = 0;
  for (unsigned i = 0; i < 16; ++i)
    initial[i] = UINT64_C(0x123456789abcdef0) ^ i;
  source[0] = source[1] = 3;
  seed = 7;
  RUN_CASE(701u, 0xc2440e57, "v28", "v4", "m2", 24, 1, SEED_LOAD("v8"), 13);
  source[0] = source[1] = 0x40000000; // Exactly 2.0 in FP32.
  RUN_CASE(704u, 0x4b441857, "v16", "v20", "m4", 2, 0, "", 2);
  RUN_CASE(707u, 0x49f79e57, "v28", "v31", "m1", 16, 0, "", 2);
  seed = UINT64_C(0x3ff0000000000000); // 1.0 + 2.0 + 2.0 = 5.0.
  RUN_CASE(709u, 0xcfc91457, "v8", "v28", "m4", 57, 1, SEED_LOAD("v18"),
           UINT64_C(0x4014000000000000));
  source[0] = source[1] = 3;
  RUN_CASE(712u, 0x4b051c57, "v24", "v16", "m4", 34, 0, "",
           UINT64_C(0x4008000000000000)); // Exactly 3.0 in FP64.
  source[0] = source[1] = 0x40000000;
  RUN_CASE(716u, 0x48879857, "v16", "v8", "m4", 12, 0, "", 2);
  printf("vew64_widen_illegal: 6 illegal + 6 legal checks, traps=%lu\n", trap_count);
  EXIT_CHECK();
}
