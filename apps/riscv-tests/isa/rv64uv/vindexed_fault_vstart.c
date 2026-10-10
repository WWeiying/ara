#include "vector_macros.h"

static uint64_t source[2] __attribute__((aligned(128))) = {
    0x1122334455667788ul, 0x8877665544332211ul};
static uint64_t target[2] __attribute__((aligned(128))) = {
    0x0123456789abcdeful, 0xfedcba9876543210ul};
static uint16_t indices[2] __attribute__((aligned(128))) = {0, 6};
static uint64_t load_result[2] __attribute__((aligned(128)));
static uint16_t three_indices[3] __attribute__((aligned(128))) = {0, 8, 14};
static uint64_t three_target[3] __attribute__((aligned(128))) = {
    0x1020304050607080ul, 0x8070605040302010ul, 0xdecafbad12345678ul};
static uint64_t three_result[3] __attribute__((aligned(128))) = {
    0x1111111111111111ul, 0x2222222222222222ul, 0x3333333333333333ul};
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

static void run_store(unsigned long restart) {
  const unsigned long vl = 2;
  asm volatile(
      "vsetvli zero, %[vl], e16, m1, tu, mu\n"
      "vle16.v v8, (%[indices])\n"
      "vsetvli zero, %[vl], e64, m1, tu, mu\n"
      "vle64.v v16, (%[source])\n"
      "csrw vstart, %[restart]\n"
      "vsoxei16.v v16, (%[target]), v8\n"
      "csrw vstart, zero\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(vl), [restart] "r"(restart), [indices] "r"(indices),
        [source] "r"(source), [target] "r"(target)
      : "memory");
}

static void run_load(unsigned long restart) {
  const unsigned long vl = 2;
  asm volatile(
      "vsetvli zero, %[vl], e16, m1, tu, mu\n"
      "vle16.v v8, (%[indices])\n"
      "vsetvli zero, %[vl], e64, m1, tu, mu\n"
      "vle64.v v16, (%[source])\n"
      "csrw vstart, %[restart]\n"
      "vloxei16.v v16, (%[target]), v8\n"
      "csrw vstart, zero\n"
      "vse64.v v16, (%[result])\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(vl), [restart] "r"(restart), [indices] "r"(indices),
        [source] "r"(source), [target] "r"(target), [result] "r"(load_result)
      : "memory");
}

static void run_load_two_prior(void) {
  const unsigned long vl = 3;
  asm volatile(
      "vsetvli zero, %[vl], e16, m1, tu, mu\n"
      "vle16.v v8, (%[indices])\n"
      "vsetvli zero, %[vl], e64, m1, tu, mu\n"
      "vle64.v v16, (%[result])\n"
      "vloxei16.v v16, (%[target]), v8\n"
      "csrw vstart, zero\n"
      "vse64.v v16, (%[result])\n"
      "fence rw, rw\n"
      :
      : [vl] "r"(vl), [indices] "r"(three_indices),
        [target] "r"(three_target), [result] "r"(three_result)
      : "memory");
}

int main(void) {
  INIT_CHECK();
  enable_vec();

  run_store(0);
  if (traps != 1 || trap_cause != 6 || trap_addr != (uintptr_t)target + 6 ||
      trap_vstart != 1 || target[0] != source[0] ||
      target[1] != 0xfedcba9876543210ul) {
    printf("indexed fault vstart=0: traps=%lu cause=%lu addr=%lx vstart=%lu target=%lx,%lx\n",
           (unsigned long)traps, (unsigned long)trap_cause,
           (unsigned long)trap_addr, (unsigned long)trap_vstart,
           (unsigned long)target[0], (unsigned long)target[1]);
    ++num_failed;
  }

  target[0] = 0x0123456789abcdeful;
  traps = trap_cause = trap_addr = trap_vstart = 0;
  run_store(1);
  if (traps != 1 || trap_cause != 6 || trap_addr != (uintptr_t)target + 6 ||
      trap_vstart != 1 || target[0] != 0x0123456789abcdeful ||
      target[1] != 0xfedcba9876543210ul) {
    printf("indexed fault vstart=1: traps=%lu cause=%lu addr=%lx vstart=%lu target=%lx,%lx\n",
           (unsigned long)traps, (unsigned long)trap_cause,
           (unsigned long)trap_addr, (unsigned long)trap_vstart,
           (unsigned long)target[0], (unsigned long)target[1]);
    ++num_failed;
  }

  traps = trap_cause = trap_addr = trap_vstart = 0;
  run_load(0);
  if (traps != 1 || trap_cause != 4 || trap_addr != (uintptr_t)target + 6 ||
      trap_vstart != 1 || load_result[0] != target[0] ||
      load_result[1] != source[1]) {
    printf("indexed load fault vstart=0: traps=%lu cause=%lu addr=%lx vstart=%lu result=%lx,%lx\n",
           (unsigned long)traps, (unsigned long)trap_cause,
           (unsigned long)trap_addr, (unsigned long)trap_vstart,
           (unsigned long)load_result[0], (unsigned long)load_result[1]);
    ++num_failed;
  }

  traps = trap_cause = trap_addr = trap_vstart = 0;
  run_load(1);
  if (traps != 1 || trap_cause != 4 || trap_addr != (uintptr_t)target + 6 ||
      trap_vstart != 1 || load_result[0] != source[0] ||
      load_result[1] != source[1]) {
    printf("indexed load fault vstart=1: traps=%lu cause=%lu addr=%lx vstart=%lu result=%lx,%lx\n",
           (unsigned long)traps, (unsigned long)trap_cause,
           (unsigned long)trap_addr, (unsigned long)trap_vstart,
           (unsigned long)load_result[0], (unsigned long)load_result[1]);
    ++num_failed;
  }

  indices[0] = 6;
  traps = trap_cause = trap_addr = trap_vstart = 0;
  run_store(0);
  if (traps != 1 || trap_cause != 6 || trap_addr != (uintptr_t)target + 6 ||
      trap_vstart != 0 || target[0] != 0x0123456789abcdeful ||
      target[1] != 0xfedcba9876543210ul) {
    printf("indexed store fault element=0: traps=%lu cause=%lu addr=%lx vstart=%lu target=%lx,%lx\n",
           (unsigned long)traps, (unsigned long)trap_cause,
           (unsigned long)trap_addr, (unsigned long)trap_vstart,
           (unsigned long)target[0], (unsigned long)target[1]);
    ++num_failed;
  }

  traps = trap_cause = trap_addr = trap_vstart = 0;
  run_load(0);
  if (traps != 1 || trap_cause != 4 || trap_addr != (uintptr_t)target + 6 ||
      trap_vstart != 0 || load_result[0] != source[0] ||
      load_result[1] != source[1]) {
    printf("indexed load fault element=0: traps=%lu cause=%lu addr=%lx vstart=%lu result=%lx,%lx\n",
           (unsigned long)traps, (unsigned long)trap_cause,
           (unsigned long)trap_addr, (unsigned long)trap_vstart,
           (unsigned long)load_result[0], (unsigned long)load_result[1]);
    ++num_failed;
  }
  indices[0] = 0;

  traps = trap_cause = trap_addr = trap_vstart = 0;
  run_load_two_prior();
  if (traps != 1 || trap_cause != 4 ||
      trap_addr != (uintptr_t)three_target + 14 || trap_vstart != 2 ||
      three_result[0] != three_target[0] ||
      three_result[1] != three_target[1] ||
      three_result[2] != 0x3333333333333333ul) {
    printf("indexed load fault element=2: traps=%lu cause=%lu addr=%lx vstart=%lu result=%lx,%lx,%lx\n",
           (unsigned long)traps, (unsigned long)trap_cause,
           (unsigned long)trap_addr, (unsigned long)trap_vstart,
           (unsigned long)three_result[0], (unsigned long)three_result[1],
           (unsigned long)three_result[2]);
    ++num_failed;
  }

  EXIT_CHECK();
}
