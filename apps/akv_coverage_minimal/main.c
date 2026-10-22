#include <stdint.h>

#include "akv_abi.h"
#include "printf.h"

static uint16_t q[128] __attribute__((aligned(64)));
static uint16_t k[128] __attribute__((aligned(64)));
static uint16_t v[128] __attribute__((aligned(64)));
static uint16_t observed[128] __attribute__((aligned(64)));
static akv_descriptor_t descriptor __attribute__((aligned(64)));

int main(void) {
  for (unsigned i = 0; i < 128; ++i) {
    q[i] = (uint16_t)(0x1100u + i);
    k[i] = (uint16_t)(0x2200u + i);
    v[i] = (uint16_t)(0x3300u + i);
    observed[i] = 0;
  }

  descriptor = (akv_descriptor_t){
      .version = AKV_DESCRIPTOR_VERSION,
      .element_format = AKV_ELEMENT_FORMAT_F16,
      .q_rows = 1,
      .head_dim = 128,
      .kv_length = 1,
      .q_row_stride_bytes = sizeof(q),
      .k_token_stride_bytes = sizeof(k),
      .v_token_stride_bytes = sizeof(v),
      .q_base = (uint64_t)(uintptr_t)q,
      .k_base = (uint64_t)(uintptr_t)k,
      .v_base = (uint64_t)(uintptr_t)v,
  };

  register uintptr_t a0 asm("a0") = (uintptr_t)&descriptor;
  register uint64_t a1 asm("a1") = 0;
  asm volatile("fence rw, rw\n"
               ".word 0x00b5205b\n"
               : "+r"(a0), "+r"(a1)
               :
               : "memory");

  a0 = akv_selector(AKV_STREAM_Q, 0);
  a1 = (uintptr_t)observed;
  asm volatile("li t0, 128\n"
               "vsetvli zero, t0, e16, m2, ta, ma\n"
               ".word 0x0205345b\n"
               "vse16.v v8, (a1)\n"
               "fence rw, rw\n"
               : "+r"(a0), "+r"(a1)
               :
               : "t0", "memory");

  for (unsigned i = 0; i < 128; ++i) {
    if (observed[i] != q[i]) {
      printf("AKV coverage mismatch at %u: got=%x expected=%x\n", i,
             observed[i], q[i]);
      return 1;
    }
  }

  asm volatile(".word 0x0000505b" : : : "memory");
  return 0;
}
