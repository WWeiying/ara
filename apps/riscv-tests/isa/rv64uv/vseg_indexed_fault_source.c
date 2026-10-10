#include "vector_macros.h"

static uint64_t source0[16] __attribute__((aligned(128)));
static uint64_t source1[16] __attribute__((aligned(128)));
static uint64_t after0[16] __attribute__((aligned(128)));
static uint64_t after1[16] __attribute__((aligned(128)));
static uint32_t indices[3] __attribute__((aligned(128))) = {0, 2, 8};
static uint32_t target[16] __attribute__((aligned(128)));
static volatile uint64_t traps;
static volatile uint64_t trap_cause;
static volatile uint64_t trap_addr;
static volatile uint64_t trap_vstart;

static void __attribute__((naked, used, aligned(4))) trap_handler(void) {
  asm volatile(
      "addi sp, sp, -32\n"
      "sd t0, 0(sp)\n"
      "sd t1, 8(sp)\n"
      "sd t2, 16(sp)\n"
      "la t1, traps\n"
      "ld t0, 0(t1)\n"
      "addi t0, t0, 1\n"
      "sd t0, 0(t1)\n"
      "la t1, trap_cause\n"
      "csrr t2, mcause\n"
      "sd t2, 0(t1)\n"
      "la t1, trap_addr\n"
      "csrr t2, mtval\n"
      "sd t2, 0(t1)\n"
      "la t1, trap_vstart\n"
      "csrr t2, vstart\n"
      "sd t2, 0(t1)\n"
      "csrr t0, mepc\n"
      "addi t0, t0, 4\n"
      "csrw mepc, t0\n"
      "ld t0, 0(sp)\n"
      "ld t1, 8(sp)\n"
      "ld t2, 16(sp)\n"
      "addi sp, sp, 32\n"
      "mret\n");
}

void rvtest_init(void) {
  asm volatile("csrw mtvec, %0" : : "r"(trap_handler) : "memory");
}

int main(void) {
  INIT_CHECK();
  enable_vec();

  for (unsigned i = 0; i < 16; ++i) {
    source0[i] = 0x100000000ul + 0x100ul * i + (0x21ul + i);
    source1[i] = 0x200000000ul + 0x100ul * i + (0x81ul + i);
    target[i] = 0xdeadbeefu;
  }

  const unsigned long full_vl = 16;
  const unsigned long store_vl = 3;
  asm volatile(
      "vsetvli zero, %[full_vl], e64, m1, tu, mu\n"
      "vle64.v v25, (%[source0])\n"
      "vle64.v v26, (%[source1])\n"
      "vsetvli zero, %[store_vl], e32, mf2, tu, mu\n"
      "vle32.v v31, (%[indices])\n"
      "vmv.v.i v0, -1\n"
      "vsoxseg2ei32.v v25, (%[target]), v31, v0.t\n"
      "csrw vstart, zero\n"
      "vsetvli zero, %[full_vl], e64, m1, tu, mu\n"
      "vse64.v v25, (%[after0])\n"
      "vse64.v v26, (%[after1])\n"
      "fence rw, rw\n"
      :
      : [full_vl] "r"(full_vl), [store_vl] "r"(store_vl),
        [source0] "r"(source0), [source1] "r"(source1),
        [indices] "r"(indices), [target] "r"(target),
        [after0] "r"(after0), [after1] "r"(after1)
      : "memory");

  if (traps != 1 || trap_cause != 6 ||
      trap_addr != (uintptr_t)target + 2 || trap_vstart != 1 ||
      target[0] != (uint32_t)source0[0] ||
      target[1] != (uint32_t)source1[0]) {
    printf("segment fault: traps=%lu cause=%lu addr=%lx vstart=%lu target=%x,%x\n",
           (unsigned long)traps, (unsigned long)trap_cause,
           (unsigned long)trap_addr, (unsigned long)trap_vstart,
           target[0], target[1]);
    ++num_failed;
  }
  for (unsigned i = 2; i < 16; ++i) {
    if (target[i] != 0xdeadbeefu) {
      printf("segment store wrote element after fault: index=%u value=%x\n",
             i, target[i]);
      ++num_failed;
      break;
    }
  }
  for (unsigned i = 0; i < 16; ++i) {
    if (after0[i] != source0[i] || after1[i] != source1[i]) {
      printf("segment source changed: index=%u got=%lx,%lx expected=%lx,%lx\n",
             i, after0[i], after1[i], source0[i], source1[i]);
      ++num_failed;
      break;
    }
  }

  EXIT_CHECK();
}
