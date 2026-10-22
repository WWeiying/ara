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

int main(void) {
  INIT_CHECK();
  enable_vec();
  enable_fp();

  asm volatile("vsetivli zero, 4, e64, m4, ta, ma\n"
               "fmv.d.x ft4, zero\n"
               "vmfgt.vf v20, v16, ft4\n" ::: "memory");
  if (trap_count != 0) {
    printf("nonoverlap vmfgt trapped: cause=%ld\n", trap_cause);
    ++num_failed;
  }

  asm volatile("vmfgt.vf v18, v16, ft4" ::: "memory");
  if (trap_count != 1 || trap_cause != 2 || trap_tval != 0x77025957u) {
    printf("overlap vmfgt: traps=%ld cause=%ld tval=%lx\n",
           trap_count, trap_cause, trap_tval);
    ++num_failed;
  }

  EXIT_CHECK();
}
