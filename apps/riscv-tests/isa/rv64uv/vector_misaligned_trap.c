#include "vector_macros.h"

static uint8_t data[16] __attribute__((aligned(16))) = {
    0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88,
};
static volatile uint64_t trap_info[4];
extern char load_fault[], store_fault[];

static void __attribute__((naked, used, aligned(4))) misaligned_handler(void) {
  asm volatile(
      "addi sp, sp, -16\n"
      "sd t0, 0(sp)\n"
      "sd t1, 8(sp)\n"
      "la t1, trap_info\n"
      "ld t0, 0(t1)\n"
      "addi t0, t0, 1\n"
      "sd t0, 0(t1)\n"
      "csrr t0, mcause\n"
      "sd t0, 8(t1)\n"
      "csrr t0, mtval\n"
      "sd t0, 16(t1)\n"
      "csrr t0, mepc\n"
      "sd t0, 24(t1)\n"
      "addi t0, t0, 4\n"
      "csrw mepc, t0\n"
      "ld t0, 0(sp)\n"
      "ld t1, 8(sp)\n"
      "addi sp, sp, 16\n"
      "mret\n");
}

void rvtest_init(void) {
  asm volatile("csrw mtvec, %0" : : "r"(misaligned_handler) : "memory");
}

static void check(unsigned id, uint64_t actual, uint64_t expected) {
  ++test_case;
  if (actual != expected) {
    printf("vector misaligned check %u: got %lx expected %lx\n",
           id, (unsigned long)actual, (unsigned long)expected);
    ++num_failed;
  }
}

int main(void) {
  uint8_t *const odd = &data[1];
  INIT_CHECK();
  enable_vec();

  trap_info[0] = 0;
  asm volatile("vsetivli zero, 1, e16, m1, ta, ma\n"
               ".balign 4\n"
               "load_fault: vle16.v v0, (%0)\n"
               : : "r"(odd) : "memory");
  check(1, trap_info[0], 1);
  check(2, trap_info[1], 4);
  check(3, trap_info[2], (uint64_t)odd);
  check(4, trap_info[3], (uint64_t)load_fault);

  trap_info[0] = 0;
  asm volatile("vsetivli zero, 1, e16, m1, ta, ma\n"
               ".balign 4\n"
               "store_fault: vse16.v v0, (%0)\n"
               : : "r"(odd) : "memory");
  check(5, trap_info[0], 1);
  check(6, trap_info[1], 6);
  check(7, trap_info[2], (uint64_t)odd);
  check(8, trap_info[3], (uint64_t)store_fault);

  EXIT_CHECK();
}
