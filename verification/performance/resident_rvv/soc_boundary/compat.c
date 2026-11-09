/* Minimal known Q4_K/Q8_K fixture, derived from qbs_akv_handoff_smoke.
 * No capability skip, admission shortcut, or alternate trap handler. */
#include <stdint.h>
#include "printf.h"
#include "qbs_abi.h"

typedef struct { uint16_t d, dmin; uint8_t scales[12], qs[128]; } q4_block_t;
typedef struct { uint32_t d_bits; int8_t qs[256]; int16_t bsums[16]; } q8_block_t;
_Static_assert(sizeof(q4_block_t) == QBS_Q4_K_BLOCK_BYTES, "Q4 layout");
_Static_assert(sizeof(q8_block_t) == QBS_Q8_K_BLOCK_BYTES, "Q8 layout");
#define Q4_BLOCK(v) { .d=0x3c00, .dmin=0, \
  .scales={[0 ... 3]=1,[8 ... 11]=1}, .qs={[0 ... 127]=((v)<<4)|(v)} }
#define Q8_BLOCK { .d_bits=0x3f800000, .qs={[0 ... 255]=1}, .bsums={[0 ... 15]=16} }
static const q4_block_t weights[3] __attribute__((aligned(64))) = {
  Q4_BLOCK(1), Q4_BLOCK(2), Q4_BLOCK(3)};
static const q8_block_t activation __attribute__((aligned(64))) = Q8_BLOCK;
static qbs_descriptor_t descriptor __attribute__((aligned(64)));
static uint32_t observed[32] __attribute__((aligned(64)));
static uint32_t source[32] __attribute__((aligned(64)));
static uint32_t rvv[32] __attribute__((aligned(64)));

unsigned boundary_compat(void) {
  const qbs_descriptor_fields_t fields = {
    .descriptor_version=QBS_DESCRIPTOR_VERSION, .weight_profile=QBS_WEIGHT_PROFILE_Q4_K,
    .activation_profile=QBS_ACTIVATION_PROFILE_Q8_K,
    .weight_layout=QBS_WEIGHT_LAYOUT_ROW_MAJOR,
    .activation_layout=QBS_ACTIVATION_LAYOUT_ROW_MAJOR, .n=3, .k_blocks=1};
  descriptor = (qbs_descriptor_t){.header=qbs_pack_descriptor_header(&fields),
                                  .weight_base=(uintptr_t)weights};
  register uintptr_t a0 __asm__("a0") = (uintptr_t)&descriptor;
  register uintptr_t a1 __asm__("a1") = (uintptr_t)&activation;
  register uintptr_t a2 __asm__("a2") = (uintptr_t)observed;
  uint64_t qbs_fcsr, rvv_fcsr;
  __asm__ volatile("csrwi fcsr, 0\nfence rw, rw\nli t0, 32\n"
                   "vsetvli zero, t0, e32, m1, ta, ma\n.word 0x00b5045b\n"
                   "vse32.v v8, (a2)\nvmv.x.s t0, v8\nfence rw, rw\nfrcsr %3"
                   : "+r"(a0), "+r"(a1), "+r"(a2), "=r"(qbs_fcsr)
                   : : "t0", "v8", "memory");
  unsigned errors = qbs_fcsr != 0;
  const uint32_t expected[3] = {0x43800000, 0x44000000, 0x44400000};
  for (unsigned i = 0; i < 32; ++i) {
    errors += observed[i] != (i < 3 ? expected[i] : 0);
    source[i] = 0x10203040u + 3*i;
  }
  a0 = (uintptr_t)source;
  a1 = (uintptr_t)rvv;
  __asm__ volatile("li t0, 32\nvsetvli zero, t0, e32, m1, ta, ma\n"
                   "vle32.v v16, (a0)\nvadd.vi v16, v16, 1\nvse32.v v16, (a1)\n"
                   "vmv.x.s t0, v16\nfence rw, rw\nfrcsr %2"
                   : "+r"(a0), "+r"(a1), "=r"(rvv_fcsr)
                   : : "t0", "v16", "memory");
  errors += rvv_fcsr != 0;
  for (unsigned i = 0; i < 32; ++i) errors += rvv[i] != source[i]+1;
  printf("PV_BOUNDARY_COMPAT qbs_fcsr=%lu rvv_fcsr=%lu qbs=", qbs_fcsr, rvv_fcsr);
  for (unsigned i = 0; i < 32; ++i) printf("%08x", observed[i]);
  printf(" rvv=");
  for (unsigned i = 0; i < 32; ++i) printf("%08x", rvv[i]);
  printf("\n");
  return errors;
}
