#include "../include/akv/akv.h"

#include <stdint.h>
#include <string.h>

#if defined(__riscv) && __riscv_xlen == 64 && defined(__riscv_vector) &&       \
    defined(__riscv_zvfh) && !defined(SPIKE)
#include <riscv_vector.h>

extern void akv_v2_compute_scores_f16_d128_gqa6(
    const uint16_t *query, float *score, uint32_t tile_tokens,
    size_t q_row_stride_bytes);
extern void akv_v2_update_outputs_f16_d128_gqa6(
    const float *score, uint16_t *accumulator, const float *old_scale,
    uint32_t tile_tokens);

static inline float negative_infinity_f32(void) {
  const uint32_t bits = UINT32_C(0xff800000);
  float value;
  memcpy(&value, &bits, sizeof(value));
  return value;
}

static inline vfloat32m2_t vector_expf(vfloat32m2_t x, size_t vl) {
  const vfloat32m2_t r = __riscv_vfmv_v_f_f32m2(0x1.8p23f, vl);
  const vfloat32m2_t z = __riscv_vfmacc_vf_f32m2(r, 0x1.715476p+0f, x, vl);
  const vfloat32m2_t n = __riscv_vfsub_vv_f32m2(z, r, vl);
  const vfloat32m2_t b = __riscv_vfnmsac_vf_f32m2(
      __riscv_vfnmsac_vf_f32m2(x, 0x1.62e4p-1f, n, vl),
      0x1.7f7d1cp-20f, n, vl);
  const vuint32m2_t e = __riscv_vsll_vx_u32m2(
      __riscv_vreinterpret_v_f32m2_u32m2(z), 23, vl);
  const vfloat32m2_t k = __riscv_vreinterpret_v_u32m2_f32m2(
      __riscv_vadd_vx_u32m2(e, UINT32_C(0x3f800000), vl));
  const vfloat32m2_t u = __riscv_vfmul_vv_f32m2(b, b, vl);
  const vfloat32m2_t j = __riscv_vfmacc_vv_f32m2(
      __riscv_vfmul_vf_f32m2(b, 0x1.ffffecp-1f, vl),
      __riscv_vfmacc_vv_f32m2(
          __riscv_vfmacc_vf_f32m2(
              __riscv_vfmv_v_f_f32m2(0x1.fffdb6p-2f, vl),
              0x1.555e66p-3f, b, vl),
          __riscv_vfmacc_vf_f32m2(
              __riscv_vfmv_v_f_f32m2(0x1.573e2ep-5f, vl),
              0x1.0e4020p-7f, b, vl),
          u, vl),
      u, vl);
  return __riscv_vfmacc_vv_f32m2(k, j, k, vl);
}

static inline float reduce_max_f32m2(vfloat32m2_t values, size_t vl) {
  const vfloat32m1_t initial =
      __riscv_vfmv_v_f_f32m1(negative_infinity_f32(), 1);
  return __riscv_vfmv_f_s_f32m1_f32(
      __riscv_vfredmax_vs_f32m2_f32m1(values, initial, vl));
}

static inline float reduce_sum_f32m2(vfloat32m2_t values, size_t vl) {
  const vfloat32m1_t initial = __riscv_vfmv_v_f_f32m1(0.0f, 1);
  return __riscv_vfmv_f_s_f32m1_f32(
      __riscv_vfredusum_vs_f32m2_f32m1(values, initial, vl));
}

static inline void issue_full(const akv_descriptor_t *descriptor,
                              uint64_t tile_start) {
  register uintptr_t a0 __asm__("a0") = (uintptr_t)descriptor;
  register uint64_t a1 __asm__("a1") = tile_start;
  __asm__ volatile("fence rw, rw\n.word 0x00b5605b"
                   : "+r"(a0), "+r"(a1)
                   :
                   : "memory");
}

static inline void issue_refill(uint64_t tile_start) {
  register uint64_t a0 __asm__("a0") = tile_start;
  __asm__ volatile(".word 0x02a0605b" : "+r"(a0) : : "memory");
}

static inline void issue_release(void) {
  __asm__ volatile(".word 0x0000505b" : : : "memory");
}

static void initialize_workspace(akv_attention_v2_workspace_t *workspace) {
  const float negative_infinity = negative_infinity_f32();
#pragma clang loop unroll(disable)
  for (uint32_t head = 0; head < AKV_ATTENTION_KERNEL_Q_ROWS; ++head) {
    size_t offset = 0;
    while (offset < AKV_HEAD_DIM_128) {
      const size_t vl = __riscv_vsetvl_e16m2(AKV_HEAD_DIM_128 - offset);
      __riscv_vse16_v_u16m2(
          workspace->accumulator[head] + offset,
          __riscv_vmv_v_x_u16m2(0u, vl), vl);
      offset += vl;
    }
    workspace->maximum[head] = negative_infinity;
    workspace->sum[head] = 0.0f;
    workspace->old_scale[head] = 0.0f;
  }
}

static __attribute__((noinline)) void apply_scale_mask_and_softmax(
    const uint16_t *mask_bits, float scale,
    akv_attention_v2_workspace_t *workspace, uint32_t tile_start,
    uint32_t tile_tokens) {
  const size_t vl = __riscv_vsetvl_e32m2(tile_tokens);
  const vfloat32m2_t mask = __riscv_vfwcvt_f_f_v_f32m2(
      __riscv_vle16_v_f16m1(
          (const _Float16 *)mask_bits + tile_start, vl),
      vl);

#pragma clang loop unroll(disable)
  for (uint32_t head = 0; head < AKV_ATTENTION_KERNEL_Q_ROWS; ++head) {
    vfloat32m2_t score =
        __riscv_vle32_v_f32m2(workspace->score[head], vl);
    score = __riscv_vfadd_vv_f32m2(
        __riscv_vfmul_vf_f32m2(score, scale, vl), mask, vl);

    const float tile_maximum = reduce_max_f32m2(score, vl);
    const float old_maximum = workspace->maximum[head];
    const float new_maximum =
        tile_maximum > old_maximum ? tile_maximum : old_maximum;
    const float old_scale = old_maximum == negative_infinity_f32()
                                ? 0.0f
                                : __builtin_expf(old_maximum - new_maximum);
    score = vector_expf(__riscv_vfsub_vf_f32m2(score, new_maximum, vl), vl);
    workspace->sum[head] =
        workspace->sum[head] * old_scale + reduce_sum_f32m2(score, vl);
    workspace->maximum[head] = new_maximum;
    workspace->old_scale[head] = old_scale;
    __riscv_vse32_v_f32m2(workspace->score[head], score, vl);
  }
}

static __attribute__((noinline)) void store_outputs(
    float *output_base, size_t output_row_stride_bytes,
    const akv_attention_v2_workspace_t *workspace) {
#pragma clang loop unroll(disable)
  for (uint32_t head = 0; head < AKV_ATTENTION_KERNEL_Q_ROWS; ++head) {
    const float inverse =
        workspace->sum[head] == 0.0f ? 0.0f : 1.0f / workspace->sum[head];
    float *output = (float *)((uint8_t *)output_base +
                             head * output_row_stride_bytes);
    size_t offset = 0;
    while (offset < AKV_HEAD_DIM_128) {
      const size_t vl = __riscv_vsetvl_e16m2(AKV_HEAD_DIM_128 - offset);
      const vfloat16m2_t accumulator = __riscv_vle16_v_f16m2(
          (const _Float16 *)workspace->accumulator[head] + offset, vl);
      __riscv_vse32_v_f32m4(
          output + offset,
          __riscv_vfmul_vf_f32m4(
              __riscv_vfwcvt_f_f_v_f32m4(accumulator, vl), inverse, vl),
          vl);
      offset += vl;
    }
  }
}
#endif

akv_status_t akv_attention_execute_v2_native(
    const akv_attention_plan_t *plan,
    akv_attention_v2_workspace_t *workspace) {
  if (plan == NULL || workspace == NULL ||
      plan->kernel_version != AKV_ATTENTION_KERNEL_VERSION_V2 ||
      !akv_v2_descriptor_is_valid(&plan->descriptor) || plan->mask == NULL ||
      plan->output == NULL ||
      plan->descriptor.q_rows != AKV_ATTENTION_KERNEL_Q_ROWS ||
      plan->descriptor.head_dim != AKV_HEAD_DIM_128 ||
      plan->output_row_stride_bytes < AKV_HEAD_DIM_128 * sizeof(float) ||
      ((uintptr_t)workspace & (AKV_DESCRIPTOR_BYTES - 1u)) != 0u)
    return AKV_STATUS_BAD_ARGUMENT;

#if defined(__riscv) && __riscv_xlen == 64 && defined(__riscv_vector) &&       \
    defined(__riscv_zvfh) && !defined(SPIKE)
  // AKV commands cross into a non-scalar memory client.  Snapshot every field
  // consumed by the following software schedule before issuing the first
  // command, so the schedule never depends on re-reading the DMA descriptor.
  const uint16_t *const query =
      (const uint16_t *)(uintptr_t)plan->descriptor.q_base;
  const uint16_t *const mask_bits = plan->mask;
  float *const output = plan->output;
  const uint32_t query_row_stride_bytes =
      plan->descriptor.q_row_stride_bytes;
  const uint32_t kv_length = plan->descriptor.kv_length;
  const size_t output_row_stride_bytes = plan->output_row_stride_bytes;
  const float scale = plan->scale;

  initialize_workspace(workspace);
  for (uint32_t tile_start = 0; tile_start < kv_length;
       tile_start += AKV_V2_TILE_TOKENS) {
    const uint32_t tile_tokens =
        akv_v2_tile_length(kv_length, tile_start);
    if (tile_start == 0u)
      issue_full(&plan->descriptor, 0u);
    else
      issue_refill(tile_start);

    akv_v2_compute_scores_f16_d128_gqa6(
        query, &workspace->score[0][0], tile_tokens,
        query_row_stride_bytes);
    apply_scale_mask_and_softmax(mask_bits, scale, workspace, tile_start,
                                 tile_tokens);
    akv_v2_update_outputs_f16_d128_gqa6(
        &workspace->score[0][0], &workspace->accumulator[0][0],
        workspace->old_scale, tile_tokens);
  }
  issue_release();
  store_outputs(output, output_row_stride_bytes, workspace);
  return AKV_STATUS_OK;
#else
  return AKV_STATUS_RUNTIME_UNAVAILABLE;
#endif
}
