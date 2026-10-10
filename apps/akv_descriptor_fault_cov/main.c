#include <stdint.h>

#include "akv_abi.h"
#include "printf.h"

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
  static akv_descriptor_t invalid_descriptor __attribute__((aligned(64)));
  static uint32_t left[32] __attribute__((aligned(16)));
  static uint32_t right[32] __attribute__((aligned(16)));
  static uint32_t observed[32] __attribute__((aligned(16)));
  register uintptr_t a0 asm("a0") = 0;
  register uintptr_t a1 asm("a1") = 0;
  unsigned failures = 0;

  for (unsigned i = 0; i < 32; ++i) {
    left[i] = i * 17 + 3;
    right[i] = i * 5 + 7;
    observed[i] = UINT32_C(0xdeadbeef);
  }

  asm volatile(".word 0x00b5205b" : "+r"(a0), "+r"(a1) : : "memory");
  if (trap_count != 1 || trap_cause != 5 || trap_tval != 0) {
    printf("AKV descriptor fault: traps=%ld cause=%ld tval=%lx\n",
           trap_count, trap_cause, trap_tval);
    ++failures;
  }

  invalid_descriptor.version = 0;
  register uintptr_t bad_address asm("a0") = (uintptr_t)&invalid_descriptor;
  register uintptr_t tile_start asm("a1") = 0;
  asm volatile(".word 0x00b5205b"
               : "+r"(bad_address), "+r"(tile_start)
               : : "memory");
  if (trap_count != 2 || trap_cause != 2) {
    printf("AKV validation fault: traps=%ld cause=%ld tval=%lx\n",
           trap_count, trap_cause, trap_tval);
    ++failures;
  }

  register uintptr_t p0 asm("a0") = (uintptr_t)left;
  register uintptr_t p1 asm("a1") = (uintptr_t)right;
  register uintptr_t p2 asm("a2") = (uintptr_t)observed;
  asm volatile("li t0, 32\n"
               "vsetvli zero, t0, e32, m1, ta, ma\n"
               "vle32.v v8, (%0)\n"
               "vle32.v v9, (%1)\n"
               "vadd.vv v10, v8, v9\n"
               "vse32.v v10, (%2)\n"
               : "+r"(p0), "+r"(p1), "+r"(p2)
               : : "t0", "memory");
  if (trap_count != 2) {
    printf("unexpected trap after AKV fault: traps=%ld cause=%ld\n",
           trap_count, trap_cause);
    ++failures;
  }
  for (unsigned i = 0; i < 32; ++i) {
    if (observed[i] != left[i] + right[i]) {
      printf("RVV recovery mismatch at %d: got=%x expected=%x\n", i,
             observed[i], left[i] + right[i]);
      ++failures;
    }
  }
  if (failures == 0)
    printf("PASSED: akv_descriptor_fault_cov\n");
  else
    printf("FAILED: akv_descriptor_fault_cov (%d)\n", failures);
  return failures;
}
