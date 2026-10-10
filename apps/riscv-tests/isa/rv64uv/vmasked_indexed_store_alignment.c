#include "vector_macros.h"

static uint64_t source[2] __attribute__((aligned(128))) = {
    0x1122334455667788ul, 0x8877665544332211ul};
static uint64_t target[2] __attribute__((aligned(128))) = {
    0x0123456789abcdeful, 0xfedcba9876543210ul};
static uint64_t follow_target[2] __attribute__((aligned(128))) = {
    0x13579bdf2468ace0ul, 0x02468ace13579bdful};
static uint16_t indices[2] __attribute__((aligned(128))) = {0, 6};
static uint64_t boundary_source[8] __attribute__((aligned(128))) = {
    0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17};
static uint64_t boundary_target[8] __attribute__((aligned(128))) = {
    0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27};
static uint16_t boundary_indices[8] __attribute__((aligned(128))) = {
    6, 6, 6, 6, 32, 6, 6, 6};
static volatile uint64_t traps;
static volatile uint64_t trap_cause;
static volatile uint64_t trap_addr;

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

static void run_store(unsigned mask, unsigned long restart) {
  const unsigned long vl = 2;
  asm volatile(
      "vsetvli zero, %[vl], e16, m1, tu, mu\n"
      "vle16.v v8, (%[indices])\n"
      "vsetvli zero, %[vl], e64, m1, tu, mu\n"
      "vle64.v v16, (%[source])\n"
      "vmv.v.x v0, %[mask]\n"
      "csrw vstart, %[restart]\n"
      "vsoxei16.v v16, (%[target]), v8, v0.t\n"
      "csrw vstart, zero\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(vl), [restart] "r"(restart), [mask] "r"(mask),
        [indices] "r"(indices), [source] "r"(source), [target] "r"(target)
      : "memory");
}

static void run_ordered_store_pair(void) {
  const unsigned long vl = 2;
  asm volatile(
      "vsetvli zero, %[vl], e16, m1, tu, mu\n"
      "vle16.v v8, (%[indices])\n"
      "vsetvli zero, %[vl], e64, m1, tu, mu\n"
      "vle64.v v16, (%[source])\n"
      "vse64.v v16, (%[target])\n"
      "vmv.v.i v0, 0\n"
      "vsoxei16.v v16, (%[target]), v8, v0.t\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(vl), [indices] "r"(indices), [source] "r"(source),
        [target] "r"(target)
      : "memory");
}

static void run_fault_followed_by_store(void) {
  const unsigned long vl = 2;
  const unsigned long restart = 1;
  asm volatile(
      "vsetvli zero, %[vl], e16, m1, tu, mu\n"
      "vle16.v v8, (%[indices])\n"
      "vsetvli zero, %[vl], e64, m1, tu, mu\n"
      "vle64.v v16, (%[source])\n"
      "vmv.v.i v0, 2\n"
      "csrw vstart, %[restart]\n"
      "vsoxei16.v v16, (%[target]), v8, v0.t\n"
      "vse64.v v16, (%[follow])\n"
      "csrw vstart, zero\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(vl), [restart] "r"(restart), [indices] "r"(indices),
        [source] "r"(source), [target] "r"(target),
        [follow] "r"(follow_target)
      : "memory");
}

static void run_boundary_store(unsigned mask) {
  const unsigned long vl = 8;
  const unsigned long restart = 4;
  asm volatile(
      "vsetvli zero, %[vl], e16, m1, tu, mu\n"
      "vle16.v v8, (%[indices])\n"
      "vsetvli zero, %[vl], e64, m1, tu, mu\n"
      "vle64.v v16, (%[source])\n"
      "vmv.v.x v0, %[mask]\n"
      "csrw vstart, %[restart]\n"
      "vsoxei16.v v16, (%[target]), v8, v0.t\n"
      "csrw vstart, zero\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(vl), [restart] "r"(restart), [mask] "r"(mask),
        [indices] "r"(boundary_indices), [source] "r"(boundary_source),
        [target] "r"(boundary_target)
      : "memory");
}

int main(void) {
  INIT_CHECK();
  enable_vec();

  run_store(0, 0);
  if (traps != 0 || target[0] != 0x0123456789abcdeful ||
      target[1] != 0xfedcba9876543210ul) {
    printf("masked indexed store vstart=0: traps=%lu target=%lx,%lx\n",
           (unsigned long)traps, (unsigned long)target[0],
           (unsigned long)target[1]);
    ++num_failed;
  }

  traps = 0;
  run_store(0, 1);
  if (traps != 0 || target[0] != 0x0123456789abcdeful ||
      target[1] != 0xfedcba9876543210ul) {
    printf("masked indexed store vstart=1: traps=%lu target=%lx,%lx\n",
           (unsigned long)traps, (unsigned long)target[0],
           (unsigned long)target[1]);
    ++num_failed;
  }

  indices[1] = 8;
  traps = 0;
  run_store(2, 1);
  if (traps != 0 || target[0] != 0x0123456789abcdeful ||
      target[1] != source[1]) {
    printf("active indexed store: traps=%lu target=%lx,%lx\n",
           (unsigned long)traps, (unsigned long)target[0],
           (unsigned long)target[1]);
    ++num_failed;
  }

  indices[1] = 6;
  traps = 0;
  run_store(2, 1);
  if (traps != 1 || trap_cause != 6 ||
      trap_addr != (uint64_t)((uintptr_t)target + 6) ||
      target[0] != 0x0123456789abcdeful || target[1] != source[1]) {
    printf("misaligned indexed store: traps=%lu cause=%lu addr=%lx target=%lx,%lx\n",
           (unsigned long)traps, (unsigned long)trap_cause,
           (unsigned long)trap_addr, (unsigned long)target[0],
           (unsigned long)target[1]);
    ++num_failed;
  }

  target[0] = 0x0123456789abcdeful;
  target[1] = 0xfedcba9876543210ul;
  traps = 0;
  run_store(1, 0);
  if (traps != 0 || target[0] != source[0] ||
      target[1] != 0xfedcba9876543210ul) {
    printf("mixed indexed store: traps=%lu target=%lx,%lx\n",
           (unsigned long)traps, (unsigned long)target[0],
           (unsigned long)target[1]);
    ++num_failed;
  }

  target[0] = 0x0123456789abcdeful;
  target[1] = 0xfedcba9876543210ul;
  traps = 0;
  run_ordered_store_pair();
  MEMORY_BARRIER;
  if (traps != 0 || target[0] != source[0] || target[1] != source[1]) {
    printf("ordered indexed store: traps=%lu target=%lx,%lx\n",
           (unsigned long)traps, (unsigned long)target[0],
           (unsigned long)target[1]);
    ++num_failed;
  }

  indices[1] = 6;
  traps = 0;
  run_fault_followed_by_store();
  if (traps != 1 || trap_cause != 6 ||
      trap_addr != (uint64_t)((uintptr_t)target + 6) ||
      follow_target[0] != 0x13579bdf2468ace0ul ||
      follow_target[1] != source[1]) {
    printf("fault then store: traps=%lu cause=%lu addr=%lx follow=%lx,%lx\n",
           (unsigned long)traps, (unsigned long)trap_cause,
           (unsigned long)trap_addr, (unsigned long)follow_target[0],
           (unsigned long)follow_target[1]);
    ++num_failed;
  }

  traps = 0;
  run_boundary_store(0);
  for (unsigned i = 0; i < 8; ++i) {
    if (traps != 0 || boundary_target[i] != 0x20 + i) {
      printf("masked indexed store vstart=4: traps=%lu target[%u]=%lx\n",
             (unsigned long)traps, i, (unsigned long)boundary_target[i]);
      ++num_failed;
      break;
    }
  }

  traps = 0;
  run_boundary_store(1u << 4);
  for (unsigned i = 0; i < 8; ++i) {
    uint64_t expected = (i == 4) ? boundary_source[4] : 0x20 + i;
    if (traps != 0 || boundary_target[i] != expected) {
      printf("mixed indexed store vstart=4: traps=%lu target[%u]=%lx expected=%lx\n",
             (unsigned long)traps, i, (unsigned long)boundary_target[i],
             (unsigned long)expected);
      ++num_failed;
      break;
    }
  }

  EXIT_CHECK();
}
