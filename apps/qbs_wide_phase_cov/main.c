#include <stdint.h>

#include "printf.h"
#include "../../software/qbs/include/qbs/qbs.h"

typedef struct {
  uint16_t d;
  uint16_t dmin;
  uint8_t scales[12];
  uint8_t qs[128];
} qbs_block_q4_k_t;

typedef struct {
  float d;
  int8_t qs[256];
  int16_t bsums[16];
} qbs_block_q8_k_t;

_Static_assert(sizeof(qbs_block_q4_k_t) == QBS_Q4_K_BLOCK_BYTES,
               "invalid Q4_K block size");
_Static_assert(sizeof(qbs_block_q8_k_t) == QBS_Q8_K_BLOCK_BYTES,
               "invalid Q8_K block size");

static const qbs_block_q4_k_t weight __attribute__((aligned(16))) = {
    .d = 0x3c00u,
    .scales = {[0 ... 3] = 1, [8 ... 11] = 1},
    .qs = {[0 ... 127] = 0x11u},
};
static const qbs_block_q8_k_t activation[8]
    __attribute__((aligned(16))) = {
        [0 ... 7] = {.d = 1.0f, .qs = {[0 ... 255] = 1},
                     .bsums = {[0 ... 15] = 16}},
};
static uint8_t packed_activation[8 * QBS_Q8_K_BLOCK_BYTES]
    __attribute__((aligned(64)));
static qbs_descriptor_t descriptor __attribute__((aligned(16)));
static uint32_t observed[8][32] __attribute__((aligned(16)));
static volatile unsigned trap_count;

void __attribute__((naked, used)) mtvec_handler(void) {
  asm volatile("la t1, trap_count\n"
               "lw t0, 0(t1)\n"
               "addi t0, t0, 1\n"
               "sw t0, 0(t1)\n"
               "csrr t0, mepc\n"
               "addi t0, t0, 4\n"
               "csrw mepc, t0\n"
               "mret\n");
}

void rvtest_init(void) {
  asm volatile("csrw mtvec, %0" : : "r"(mtvec_handler) : "memory");
}

int main(void) {
  const qbs_descriptor_fields_t fields = {
      .descriptor_version = QBS_DESCRIPTOR_VERSION,
      .weight_profile = QBS_WEIGHT_PROFILE_Q4_K,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
      .weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR,
      .activation_layout = QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED,
      .n = 1,
      .k_blocks = 1,
  };
  qbs_status_t status = qbs_pack_activation_m8_grouped(
      QBS_ACTIVATION_PROFILE_Q8_K, activation, sizeof(activation), 8, 1,
      packed_activation, sizeof(packed_activation));
  if (status != QBS_STATUS_OK) {
    printf("QBS M8 activation pack failed: status=%d\n", status);
    return 1;
  }
  descriptor.header = qbs_pack_descriptor_header(&fields);
  descriptor.weight_base = (uintptr_t)&weight;

  register uintptr_t a0 asm("a0") = (uintptr_t)&descriptor;
  register uintptr_t a1 asm("a1") = (uintptr_t)packed_activation;
  register uintptr_t a2 asm("a2") = (uintptr_t)observed;
  register uintptr_t a3 asm("a3") = sizeof(observed[0]);
  asm volatile("fence rw, rw\n"
               "li t0, 256\n"
               "vsetvli zero, t0, e32, m8, ta, ma\n"
               ".word 0x0eb5045b\n"
               "li t0, 1\n"
               "vsetvli zero, t0, e32, m1, ta, ma\n"
               "mv t1, a2\n"
               "vse32.v v8, (t1)\n"
               "add t1, t1, a3\n"
               "vse32.v v9, (t1)\n"
               "add t1, t1, a3\n"
               "vse32.v v10, (t1)\n"
               "add t1, t1, a3\n"
               "vse32.v v11, (t1)\n"
               "add t1, t1, a3\n"
               "vse32.v v12, (t1)\n"
               "add t1, t1, a3\n"
               "vse32.v v13, (t1)\n"
               "add t1, t1, a3\n"
               "vse32.v v14, (t1)\n"
               "add t1, t1, a3\n"
               "vse32.v v15, (t1)\n"
               : "+r"(a0), "+r"(a1), "+r"(a2), "+r"(a3)
               : : "t0", "t1", "v8", "v9", "v10", "v11", "v12",
                   "v13", "v14", "v15", "memory");

  unsigned failures = trap_count != 0;
  if (trap_count)
    printf("QBS M8 instruction trapped: count=%d\n", trap_count);
  for (unsigned context = 0; context < 8; ++context) {
    if (observed[context][0] != UINT32_C(0x43800000)) {
      printf("QBS context %d: got=%x expected=43800000\n", context,
             observed[context][0]);
      ++failures;
    }
    for (unsigned element = 1; element < 32; ++element) {
      if (observed[context][element] != 0) {
        printf("QBS tail changed at %d,%d: got=%x\n", context, element,
               observed[context][element]);
        ++failures;
      }
    }
  }
  if (failures == 0)
    printf("PASSED: qbs_wide_phase_cov\n");
  else
    printf("FAILED: qbs_wide_phase_cov (%d)\n", failures);
  return failures;
}
