#include "vector_macros.h"

static volatile uint64_t trap_count;
static volatile uint64_t trap_cause;
static volatile uint64_t trap_tval;

void __attribute__((naked, used)) mtvec_handler(void) {
  asm volatile("csrr t0, mcause\n"
               "la t1, trap_cause\n"
               "sd t0, 0(t1)\n"
               "csrr t0, mtval\n"
               "la t1, trap_tval\n"
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

static void expect_illegal(const char *name, uint64_t before, uint32_t insn) {
  if (trap_count != before + 1 || trap_cause != 2 || trap_tval != insn) {
    printf("%s: traps=%ld cause=%ld tval=%lx expected=%x\n", name,
           trap_count - before, trap_cause, trap_tval, insn);
    ++num_failed;
  }
}

int main(void) {
  INIT_CHECK();
  enable_vec();

  uint64_t reduced = 0;
  asm volatile("vsetivli zero, 1, e32, m1, ta, ma\n"
               "vmv.v.i v14, 0\n"
               "vsetivli zero, 4, e16, m8, ta, ma\n"
               "vmv.v.i v16, 1\n"
               "vwredsumu.vs v14, v16, v14\n"
               "vsetivli zero, 1, e32, m1, ta, ma\n"
               "vmv.x.s %0, v14\n"
               : "=r"(reduced) : : "memory");
  if (trap_count != 0 || reduced != 4) {
    printf("legal m8 widening reduction: traps=%ld result=%ld\n",
           trap_count, reduced);
    ++num_failed;
  }

  asm volatile("vsetivli zero, 4, e32, m8, ta, ma\n"
               "vadd.vv v16, v0, v24\n" ::: "memory");
  if (trap_count != 0) {
    printf("legal m8 vadd trapped: cause=%ld\n", trap_cause);
    ++num_failed;
  }

  uint64_t before = trap_count;
  asm volatile("vwadd.wv v16, v0, v24, v0.t" ::: "memory");
  expect_illegal("wide EMUL > 8", before, 0xd40c2857u);

  before = trap_count;
  asm volatile("vsetivli zero, 4, e64, m8, ta, ma\n"
               "vzext.vf8 v16, v24\n" ::: "memory");
  if (trap_count != before) {
    printf("legal vzext trapped: cause=%ld\n", trap_cause);
    ++num_failed;
  }

  asm volatile("vzext.vf8 v16, v23" ::: "memory");
  if (trap_count != before) {
    printf("legal high-overlap vzext trapped: cause=%ld\n", trap_cause);
    ++num_failed;
  }

  before = trap_count;
  asm volatile("vzext.vf8 v16, v17" ::: "memory");
  expect_illegal("vzext low overlap", before, 0x4b112857u);

  EXIT_CHECK();
}
