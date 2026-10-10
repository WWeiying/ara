#include "vector_macros.h"

static uint64_t data[2] __attribute__((aligned(128))) = {0x1122334455667788ul,
                                                        0x8877665544332211ul};
static uint16_t indices[8] __attribute__((aligned(128))) = {0, 6, 6, 6, 0, 6, 6, 6};
static volatile uint64_t output[8] __attribute__((aligned(128)));
static volatile uint64_t traps;

static void __attribute__((naked, used, aligned(4))) trap_handler(void) {
  asm volatile(
      "addi sp, sp, -16\n"
      "sd t0, 0(sp)\n"
      "sd t1, 8(sp)\n"
      "la t1, traps\n"
      "ld t0, 0(t1)\n"
      "addi t0, t0, 1\n"
      "sd t0, 0(t1)\n"
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

static void run_indexed(unsigned mask, unsigned long restart, unsigned long vl) {
  asm volatile(
      "vsetvli zero, %[vl], e16, m1, tu, mu\n"
      "vle16.v v8, (%[indices])\n"
      "vsetvli zero, %[vl], e64, m1, tu, mu\n"
      "vmv.v.i v16, 7\n"
      "vmv.v.x v0, %[mask]\n"
      "csrw vstart, %[restart]\n"
      "vloxei16.v v16, (%[data]), v8, v0.t\n"
      "csrw vstart, zero\n"
      "vse64.v v16, (%[output])\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(vl), [restart] "r"(restart), [mask] "r"(mask),
        [indices] "r"(indices), [data] "r"(data), [output] "r"(output)
      : "memory");
}

int main(void) {
  INIT_CHECK();
  enable_vec();

  traps = 0;
  run_indexed(0, 0, 2);
  if (traps != 0 || output[0] != 7 || output[1] != 7) {
    printf("masked indexed load vstart=0: traps=%lu output=%lx,%lx\n",
           (unsigned long)traps, (unsigned long)output[0],
           (unsigned long)output[1]);
    ++num_failed;
  }

  traps = 0;
  run_indexed(0, 1, 2);
  if (traps != 0 || output[0] != 7 || output[1] != 7) {
    printf("masked indexed load vstart=1: traps=%lu output=%lx,%lx\n",
           (unsigned long)traps, (unsigned long)output[0],
           (unsigned long)output[1]);
    ++num_failed;
  }

  traps = 0;
  run_indexed(1, 0, 2);
  if (traps != 0 || output[0] != data[0] || output[1] != 7) {
    printf("mixed indexed load: traps=%lu output=%lx,%lx\n",
           (unsigned long)traps, (unsigned long)output[0],
           (unsigned long)output[1]);
    ++num_failed;
  }

  indices[1] = 8;
  traps = 0;
  run_indexed(2, 1, 2);
  if (traps != 0 || output[0] != 7 || output[1] != data[1]) {
    printf("active indexed load: traps=%lu output=%lx,%lx\n",
           (unsigned long)traps, (unsigned long)output[0],
           (unsigned long)output[1]);
    ++num_failed;
  }

  traps = 0;
  run_indexed(0, 4, 8);
  for (unsigned i = 0; i < 8; ++i) {
    if (traps != 0 || output[i] != 7) {
      printf("masked indexed load vstart=4: traps=%lu output[%u]=%lx\n",
             (unsigned long)traps, i, (unsigned long)output[i]);
      ++num_failed;
      break;
    }
  }

  traps = 0;
  run_indexed(1u << 4, 4, 8);
  for (unsigned i = 0; i < 8; ++i) {
    uint64_t expected = (i == 4) ? data[0] : 7;
    if (traps != 0 || output[i] != expected) {
      printf("mixed indexed load vstart=4: traps=%lu output[%u]=%lx expected=%lx\n",
             (unsigned long)traps, i, (unsigned long)output[i],
             (unsigned long)expected);
      ++num_failed;
      break;
    }
  }

  EXIT_CHECK();
}
