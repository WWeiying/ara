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
  static uint16_t k_row[64] __attribute__((aligned(64)));
  static uint16_t v_row[64] __attribute__((aligned(64)));
  static akv_descriptor_t descriptor __attribute__((aligned(64)));
  static uint32_t left[32] __attribute__((aligned(16)));
  static uint32_t observed[32] __attribute__((aligned(16)));
  unsigned failures = 0;

  descriptor.version = AKV_DESCRIPTOR_VERSION;
  descriptor.element_format = AKV_ELEMENT_FORMAT_F16;
  descriptor.q_rows = 1;
  descriptor.head_dim = 64;
  descriptor.kv_length = 1;
  descriptor.q_row_stride_bytes = 128;
  descriptor.k_token_stride_bytes = 128;
  descriptor.v_token_stride_bytes = 128;
  descriptor.q_base = 0;
  descriptor.k_base = (uintptr_t)k_row;
  descriptor.v_base = (uintptr_t)v_row;

  register uintptr_t a0 asm("a0") = (uintptr_t)&descriptor;
  register uintptr_t a1 asm("a1") = 0;
  asm volatile(".word 0x00b5205b" : "+r"(a0), "+r"(a1) : : "memory");
  if (trap_count != 1 || trap_cause != 5 || trap_tval != 0) {
    printf("AKV payload fault: traps=%ld cause=%ld tval=%lx\n",
           trap_count, trap_cause, trap_tval);
    ++failures;
  }

  for (unsigned i = 0; i < 32; ++i) {
    left[i] = i * 13 + 11;
    observed[i] = 0;
  }
  register uintptr_t p0 asm("a0") = (uintptr_t)left;
  register uintptr_t p1 asm("a1") = (uintptr_t)observed;
  asm volatile("li t0, 32\n"
               "vsetvli zero, t0, e32, m1, ta, ma\n"
               "vle32.v v8, (%0)\n"
               "vadd.vv v9, v8, v8\n"
               "vse32.v v9, (%1)\n"
               : "+r"(p0), "+r"(p1) : : "t0", "memory");
  if (trap_count != 1) {
    printf("unexpected trap after payload fault: traps=%ld cause=%ld\n",
           trap_count, trap_cause);
    ++failures;
  }
  for (unsigned i = 0; i < 32; ++i) {
    if (observed[i] != 2 * left[i]) {
      printf("RVV recovery mismatch at %d: got=%x expected=%x\n", i,
             observed[i], 2 * left[i]);
      ++failures;
    }
  }
  if (failures == 0)
    printf("PASSED: akv_payload_fault_cov\n");
  else
    printf("FAILED: akv_payload_fault_cov (%d)\n", failures);
  return failures;
}
