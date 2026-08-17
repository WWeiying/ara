// Check that a rejected vector memory request does not block trap-handler or
// post-trap scalar memory operations.

#include "vector_macros.h"

static volatile uint64_t trap_cause;
static volatile uint64_t recovery_store;

void __attribute__((naked, used)) mtvec_handler(void) {
  asm volatile(
      "csrr t0, mcause\n"
      "la t1, trap_cause\n"
      // This is intentionally the first explicit memory operation in the
      // handler. It cannot issue while CVA6 retains a phantom vector load.
      "sd t0, 0(t1)\n"
      "csrr t0, mepc\n"
      "addi t0, t0, 4\n"
      "csrw mepc, t0\n"
      "mret\n");
}

// crt0 invokes this weak hook in M-mode before entering main in U-mode.
void rvtest_init(void) {
  asm volatile("csrw mtvec, %0" : : "r"(mtvec_handler) : "memory");
}

int main(void) {
  INIT_CHECK();
  enable_vec();
  trap_cause = 0;
  recovery_store = 0;

  asm volatile(
      "vsetivli zero, 16, e8, m2, ta, ma\n"
      // Eight EMUL=2 fields starting at v18 extend past v31. CVA6 classifies
      // this as a vector load, but Ara must reject it before entering VLSU.
      ".word 0xeb1b0907\n"
      :
      :
      : "ra", "t0", "t1", "t2", "t3", "t4", "t5", "t6", "a0", "a1",
        "a2", "a3", "a4", "a5", "a6", "a7", "memory");

  recovery_store = 0x5a5aa5a55a5aa5a5UL;
  if (trap_cause != 2 || recovery_store != 0x5a5aa5a55a5aa5a5UL) {
    printf("illegal segment recovery failed: mcause=%lx store=%lx\n",
           trap_cause, recovery_store);
    ++num_failed;
  }

  EXIT_CHECK();
}
