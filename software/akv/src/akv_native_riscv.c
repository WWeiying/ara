#include "../include/akv/akv.h"

#include <stdint.h>

#if defined(__riscv) && __riscv_xlen == 64 && defined(__riscv_vector) &&       \
    defined(__riscv_zvfh) && !defined(SPIKE)
extern void
akv_attention_group_f16_d128_gqa6(const akv_descriptor_t *descriptor,
                                  const uint16_t *mask, float *output,
                                  size_t output_row_stride_bytes, float scale);
#endif

uint64_t akv_native_info(void *context, unsigned index) {
  (void)context;
#if defined(__riscv) && __riscv_xlen == 64 && !defined(SPIKE)
  register uintptr_t a0 __asm__("a0") = index;
  __asm__ volatile(".word 0x0005455b" : "+r"(a0) : : "memory");
  return a0;
#else
  (void)index;
  return 0u;
#endif
}

akv_status_t akv_native_execute(void *context,
                                const akv_descriptor_t *descriptor,
                                const uint16_t *mask, float *output,
                                size_t output_row_stride_bytes, float scale) {
  (void)context;
  if (descriptor == NULL || mask == NULL || output == NULL ||
      !akv_descriptor_is_valid(descriptor) ||
      descriptor->q_rows != AKV_ATTENTION_KERNEL_Q_ROWS ||
      descriptor->head_dim != AKV_HEAD_DIM_128 ||
      output_row_stride_bytes < AKV_HEAD_DIM_128 * sizeof(float))
    return AKV_STATUS_BAD_ARGUMENT;
#if defined(__riscv) && __riscv_xlen == 64 && defined(__riscv_vector) &&       \
    defined(__riscv_zvfh) && !defined(SPIKE)
  akv_attention_group_f16_d128_gqa6(descriptor, mask, output,
                                    output_row_stride_bytes, scale);
  return AKV_STATUS_OK;
#else
  (void)output_row_stride_bytes;
  (void)scale;
  return AKV_STATUS_RUNTIME_UNAVAILABLE;
#endif
}

akv_status_t akv_attention_execute_native(const akv_attention_plan_t *plan) {
  if (plan == NULL || plan->kernel_version != AKV_ATTENTION_KERNEL_VERSION ||
      plan->mask == NULL || plan->output == NULL)
    return AKV_STATUS_BAD_ARGUMENT;
#if defined(__riscv) && __riscv_xlen == 64 && defined(__riscv_vector) &&       \
    defined(__riscv_zvfh) && !defined(SPIKE)
  akv_attention_group_f16_d128_gqa6(&plan->descriptor, plan->mask, plan->output,
                                    plan->output_row_stride_bytes, plan->scale);
  return AKV_STATUS_OK;
#else
  return AKV_STATUS_RUNTIME_UNAVAILABLE;
#endif
}
