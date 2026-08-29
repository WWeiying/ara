#include "qbs/qbs.h"

#include <stdint.h>

uint64_t qbs_native_info(void *context, unsigned index) {
  (void)context;
#if defined(__riscv) && __riscv_xlen == 64
  register uintptr_t a0 __asm__("a0") = index;
  __asm__ volatile(".word 0x0005155b" : "+r"(a0) : : "memory");
  return a0;
#else
  (void)index;
  return 0;
#endif
}

qbs_status_t qbs_native_execute_command(
    void *context, const qbs_descriptor_v1_t *descriptor, unsigned m,
    const void *activations, float *output, size_t output_stride_elements,
    unsigned n, int segmented) {
  (void)context;
  (void)segmented;
  if (descriptor == NULL || activations == NULL || output == NULL ||
      m == 0 || m > QBS_MAX_M || n == 0 || n > QBS_MAX_N)
    return QBS_STATUS_BAD_ARGUMENT;
#if defined(__riscv) && __riscv_xlen == 64
  register uintptr_t a0 __asm__("a0") = (uintptr_t)descriptor;
  register uintptr_t a1 __asm__("a1") = (uintptr_t)activations;
  switch (m) {
    case 1: {
      register uintptr_t a2 __asm__("a2") = (uintptr_t)output;
      __asm__ volatile(
          "fence rw, rw\n"
          "li t0, 32\n"
          "vsetvli zero, t0, e32, m1, ta, ma\n"
          ".word 0x00b5045b\n"
          "mv t0, %[n]\n"
          "vsetvli zero, t0, e32, m1, ta, ma\n"
          "vse32.v v8, (a2)\n"
          : "+r"(a0), "+r"(a1), "+r"(a2)
          : [n] "r"(n)
          : "t0", "v8", "memory");
      break;
    }
    case 2: {
      register uintptr_t a2 __asm__("a2") = (uintptr_t)output;
      register uintptr_t a3 __asm__("a3") =
          (uintptr_t)(output + output_stride_elements);
      __asm__ volatile(
          "fence rw, rw\n"
          "li t0, 64\n"
          "vsetvli zero, t0, e32, m2, ta, ma\n"
          ".word 0x02b5045b\n"
          "mv t0, %[n]\n"
          "vsetvli zero, t0, e32, m1, ta, ma\n"
          "vse32.v v8, (a2)\n"
          "vse32.v v9, (a3)\n"
          : "+r"(a0), "+r"(a1), "+r"(a2), "+r"(a3)
          : [n] "r"(n)
          : "t0", "v8", "v9", "memory");
      break;
    }
    case 3: {
      register uintptr_t a2 __asm__("a2") = (uintptr_t)output;
      register uintptr_t a3 __asm__("a3") =
          (uintptr_t)(output + output_stride_elements);
      register uintptr_t a4 __asm__("a4") =
          (uintptr_t)(output + 2u * output_stride_elements);
      __asm__ volatile(
          "fence rw, rw\n"
          "li t0, 128\n"
          "vsetvli zero, t0, e32, m4, ta, ma\n"
          ".word 0x04b5045b\n"
          "mv t0, %[n]\n"
          "vsetvli zero, t0, e32, m1, ta, ma\n"
          "vse32.v v8, (a2)\n"
          "vse32.v v9, (a3)\n"
          "vse32.v v10, (a4)\n"
          : "+r"(a0), "+r"(a1), "+r"(a2), "+r"(a3), "+r"(a4)
          : [n] "r"(n)
          : "t0", "v8", "v9", "v10", "v11", "memory");
      break;
    }
    case 4: {
      register uintptr_t a2 __asm__("a2") = (uintptr_t)output;
      register uintptr_t a3 __asm__("a3") =
          (uintptr_t)(output + output_stride_elements);
      register uintptr_t a4 __asm__("a4") =
          (uintptr_t)(output + 2u * output_stride_elements);
      register uintptr_t a5 __asm__("a5") =
          (uintptr_t)(output + 3u * output_stride_elements);
      __asm__ volatile(
          "fence rw, rw\n"
          "li t0, 128\n"
          "vsetvli zero, t0, e32, m4, ta, ma\n"
          ".word 0x06b5045b\n"
          "mv t0, %[n]\n"
          "vsetvli zero, t0, e32, m1, ta, ma\n"
          "vse32.v v8, (a2)\n"
          "vse32.v v9, (a3)\n"
          "vse32.v v10, (a4)\n"
          "vse32.v v11, (a5)\n"
          : "+r"(a0), "+r"(a1), "+r"(a2), "+r"(a3), "+r"(a4),
            "+r"(a5)
          : [n] "r"(n)
          : "t0", "v8", "v9", "v10", "v11", "memory");
      break;
    }
  }
  return QBS_STATUS_OK;
#else
  (void)output_stride_elements;
  return QBS_STATUS_RUNTIME_UNAVAILABLE;
#endif
}
