#include "vector_macros.h"

#define UNMAPPED_STORE_ADDR 0xe0000000ul

static volatile uint64_t trap_info[6];
static volatile uint64_t younger_store_committed;
static uint64_t source[8] __attribute__((aligned(64)));
extern char store_fault_bursts[];

#ifdef SPIKE_REFERENCE
volatile uint64_t tohost __attribute__((used, aligned(64)));
volatile uint64_t fromhost __attribute__((used, aligned(64)));
#endif

static void __attribute__((naked, used, aligned(4))) trap_handler(void) {
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
      "csrr t0, vstart\n"
      "sd t0, 32(t1)\n"
      "la t1, younger_store_committed\n"
      "ld t0, 0(t1)\n"
      "la t1, trap_info\n"
      "sd t0, 40(t1)\n"
      "csrr t0, mepc\n"
      "addi t0, t0, 4\n"
      "csrw mepc, t0\n"
      "ld t0, 0(sp)\n"
      "ld t1, 8(sp)\n"
      "addi sp, sp, 16\n"
      "mret\n");
}

void rvtest_init(void) {
  asm volatile("csrw mtvec, %0" : : "r"(trap_handler) : "memory");
}

static void check(unsigned id, uint64_t actual, uint64_t expected) {
  ++test_case;
  if (actual != expected) {
    printf("multi-burst store fault %u: got %lx expected %lx\n", id,
           (unsigned long)actual, (unsigned long)expected);
    ++num_failed;
  }
}

int main(void) {
  INIT_CHECK();
  enable_vec();

  const unsigned long avl = 8;
  const unsigned long stride = 64;
  unsigned long vl;
  asm volatile("vsetvli %0, %1, e64, m1, ta, ma" : "=r"(vl) : "r"(avl));
  check(1, vl, avl);
  asm volatile("vle64.v v8, (%1)\n"
               ".balign 4\n"
               "store_fault_bursts: vsse64.v v8, (%0), %2\n"
               "li t2, 1\n"
               "sd t2, 0(%3)\n"
               "fence rw, rw\n"
               : : "r"(UNMAPPED_STORE_ADDR), "r"(source), "r"(stride),
                   "r"(&younger_store_committed) : "t2", "memory");

  check(2, trap_info[0], 1);
  check(3, trap_info[1], 7);
  check(4, trap_info[2], UNMAPPED_STORE_ADDR);
  check(5, trap_info[3], (uint64_t)store_fault_bursts);
  check(6, trap_info[4], 0);
  check(7, trap_info[5], 0);
  check(8, younger_store_committed, 1);

#ifdef SPIKE_REFERENCE
  fromhost = 0;
  tohost = ((uint64_t)num_failed << 1) | 1;
  for (;;)
    asm volatile("wfi");
#endif
  EXIT_CHECK();
}
