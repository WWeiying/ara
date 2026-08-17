// Check RVV operations that architecturally require vstart=0.

#include "vector_macros.h"

static volatile uint64_t trap_count;
static volatile uint64_t trap_cause;
static volatile uint64_t trap_vstart;

void __attribute__((naked, used)) mtvec_handler(void) {
  asm volatile("csrr t0, mcause\n"
               "la t1, trap_cause\n"
               "sd t0, 0(t1)\n"
               "csrr t0, vstart\n"
               "la t1, trap_vstart\n"
               "sd t0, 0(t1)\n"
               "la t1, trap_count\n"
               "ld t0, 0(t1)\n"
               "addi t0, t0, 1\n"
               "sd t0, 0(t1)\n"
               "csrr t0, mepc\n"
               "addi t0, t0, 4\n"
               "csrw mepc, t0\n"
               "mret\n");
}

void rvtest_init(void) {
  asm volatile("csrw mtvec, %0" : : "r"(mtvec_handler) : "memory");
}

#define EXPECT_VSTART_ILLEGAL(NAME, INSN)                                      \
  do {                                                                         \
    uint64_t before = trap_count;                                              \
    trap_cause = 0;                                                            \
    trap_vstart = 0;                                                           \
    asm volatile("li t2, 1\n"                                                  \
                 "csrw vstart, t2\n" INSN "\n"                                 \
                 :                                                             \
                 :                                                             \
                 : "t2", "t3", "memory");                                      \
    if (trap_count != before + 1 || trap_cause != 2 || trap_vstart != 1) {     \
      printf(NAME " failed: traps=%ld cause=%ld vstart=%ld\n",                 \
             trap_count - before, trap_cause, trap_vstart);                    \
      ++num_failed;                                                            \
    }                                                                          \
  } while (0)

int main(void) {
  INIT_CHECK();
  enable_vec();
  trap_count = 0;

  asm volatile("vsetivli zero, 8, e8, m1, tu, mu" ::: "memory");
  EXPECT_VSTART_ILLEGAL("vredsum", "vredsum.vs v8, v10, v9");
  EXPECT_VSTART_ILLEGAL("vcpop", "vpopc.m t3, v10");
  EXPECT_VSTART_ILLEGAL("vfirst", "vfirst.m t3, v10");
  EXPECT_VSTART_ILLEGAL("vmsbf", "vmsbf.m v8, v10");
  EXPECT_VSTART_ILLEGAL("vmsof", "vmsof.m v8, v10");
  EXPECT_VSTART_ILLEGAL("vmsif", "vmsif.m v8, v10");
  EXPECT_VSTART_ILLEGAL("viota", "viota.m v8, v10");
  EXPECT_VSTART_ILLEGAL("vcompress", "vcompress.vm v8, v10, v0");
  asm volatile("csrw vstart, zero" ::: "memory");

  EXIT_CHECK();
}
