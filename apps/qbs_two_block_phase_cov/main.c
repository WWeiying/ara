#include <stdint.h>

#include "printf.h"
#include "qbs_abi.h"

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

static const qbs_block_q4_k_t weights[2] __attribute__((aligned(16))) = {
    {.d = 0x3c00u, .scales = {[0 ... 3] = 1, [8 ... 11] = 1},
     .qs = {[0 ... 127] = 0x11u}},
    {.d = 0x3c00u, .scales = {[0 ... 3] = 1, [8 ... 11] = 1},
     .qs = {[0 ... 127] = 0x11u}},
};
static const qbs_block_q8_k_t activation[2] __attribute__((aligned(16))) = {
    {.d = 1.0f, .qs = {[0 ... 255] = 1}, .bsums = {[0 ... 15] = 16}},
    {.d = 1.0f, .qs = {[0 ... 255] = 1}, .bsums = {[0 ... 15] = 16}},
};
static qbs_descriptor_t descriptor __attribute__((aligned(16)));
static uint32_t observed[32] __attribute__((aligned(16)));

int main(void) {
  const qbs_descriptor_fields_t fields = {
      .descriptor_version = QBS_DESCRIPTOR_VERSION,
      .weight_profile = QBS_WEIGHT_PROFILE_Q4_K,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
      .weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR,
      .activation_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR,
      .n = 1,
      .k_blocks = 2,
  };
  descriptor.header = qbs_pack_descriptor_header(&fields);
  descriptor.weight_base = (uintptr_t)weights;

  register uintptr_t a0 asm("a0") = (uintptr_t)&descriptor;
  register uintptr_t a1 asm("a1") = (uintptr_t)activation;
  register uintptr_t a2 asm("a2") = (uintptr_t)observed;
  asm volatile("li t0, 32\n"
               "vsetvli zero, t0, e32, m1, ta, ma\n"
               ".word 0x00b5045b\n"
               "vse32.v v8, (a2)\n"
               : "+r"(a0), "+r"(a1), "+r"(a2)
               : : "t0", "memory");

  unsigned failures = 0;
  if (observed[0] != UINT32_C(0x44000000)) {
    printf("QBS result mismatch: got=%x expected=44000000\n", observed[0]);
    ++failures;
  }
  for (unsigned i = 1; i < 32; ++i) {
    if (observed[i] != 0) {
      printf("QBS tail changed at %d: got=%x\n", i, observed[i]);
      ++failures;
    }
  }
  if (failures == 0)
    printf("PASSED: qbs_two_block_phase_cov\n");
  else
    printf("FAILED: qbs_two_block_phase_cov (%d)\n", failures);
  return failures;
}
