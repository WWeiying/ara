#include <stdint.h>

#include "printf.h"
#include "qbs_abi.h"

typedef struct {
  float d;
  int8_t qs[256];
  int16_t bsums[16];
} qbs_block_q8_k_t;

_Static_assert(sizeof(qbs_block_q8_k_t) == QBS_Q8_K_BLOCK_BYTES,
               "invalid Q8_K block size");

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
  static qbs_descriptor_t descriptor __attribute__((aligned(16)));
  static qbs_block_q8_k_t activation __attribute__((aligned(16)));
  static uint32_t source[32] __attribute__((aligned(16)));
  static uint32_t observed[32] __attribute__((aligned(16)));
  unsigned failures = 0;
  const qbs_descriptor_fields_t fields = {
      .descriptor_version = QBS_DESCRIPTOR_VERSION,
      .weight_profile = QBS_WEIGHT_PROFILE_Q4_K,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
      .weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR,
      .activation_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR,
      .n = 5,
      .k_blocks = 1,
  };

  descriptor.header = qbs_pack_descriptor_header(&fields);
  descriptor.weight_base = 0;
  activation.d = 1.0f;
  for (unsigned i = 0; i < 32; ++i) {
    source[i] = UINT32_C(0x41800000) + i;
    observed[i] = 0;
  }

  register uintptr_t a0 asm("a0") = (uintptr_t)&descriptor;
  register uintptr_t a1 asm("a1") = (uintptr_t)&activation;
  register uintptr_t a2 asm("a2") = (uintptr_t)source;
  register uintptr_t a3 asm("a3") = (uintptr_t)observed;
  asm volatile("li t0, 32\n"
               "vsetvli zero, t0, e32, m1, ta, ma\n"
               "vle32.v v8, (a2)\n"
               ".word 0x00b5045b\n"
               "vse32.v v8, (a3)\n"
               : "+r"(a0), "+r"(a1), "+r"(a2), "+r"(a3)
               : : "t0", "memory");

  if (trap_count != 1 || trap_cause != 5 || trap_tval != 0) {
    printf("QBS weight fault: traps=%ld cause=%ld tval=%lx\n",
           trap_count, trap_cause, trap_tval);
    ++failures;
  }
  for (unsigned i = 0; i < 32; ++i) {
    if (observed[i] != source[i]) {
      printf("QBS destination changed at %d: got=%x expected=%x\n", i,
             observed[i], source[i]);
      ++failures;
    }
  }
  if (failures == 0)
    printf("PASSED: qbs_weight_fault_cov\n");
  else
    printf("FAILED: qbs_weight_fault_cov (%d)\n", failures);
  return failures;
}
