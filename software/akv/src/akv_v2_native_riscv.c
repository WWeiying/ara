#include "../include/akv/akv.h"
#include "akv_prefill_internal.h"

#include <stdint.h>
#include <string.h>

#ifndef AKV_PROFILE_PHASE
#define AKV_PROFILE_PHASE(phase) do { (void)(phase); } while (0)
#endif

enum {
  AKV_PROFILE_PHASE_QUERY = 1,
  AKV_PROFILE_PHASE_KV = 2,
  AKV_PROFILE_PHASE_COMPUTE = 3,
};

_Static_assert(
    sizeof(((akv_attention_v2_prefill_workspace_t *)0)->query[0][0]) ==
        AKV_HEAD_DIM_128 * sizeof(uint16_t),
    "Prefill score kernels require contiguous Query rows");

static inline int common_v2_plan_is_valid(
    const akv_attention_plan_t *plan) {
  return plan != NULL &&
         plan->kernel_version == AKV_ATTENTION_KERNEL_VERSION_V2 &&
         plan->d_segment_count == 1u && plan->d_offset == 0u &&
         plan->d_count == plan->descriptor.head_dim &&
         plan->logical_head_dim == plan->descriptor.head_dim &&
         plan->mask != NULL && plan->output != NULL &&
         plan->reserved[0] == 0u && plan->scale > 0.0f &&
         plan->scale <= 0x1.fffffep+127f &&
         akv_attention_v2_shape_supported(plan->descriptor.q_rows,
                                          plan->descriptor.head_dim) &&
         akv_v2_descriptor_is_valid(&plan->descriptor) &&
         plan->output_row_stride_bytes >=
             (size_t)plan->descriptor.head_dim * sizeof(float);
}

#if defined(__riscv) && __riscv_xlen == 64 && defined(__riscv_vector) &&       \
    defined(__riscv_zvfh) && !defined(SPIKE)
#include <riscv_vector.h>

extern void akv_v2_compute_scores_f16_d128_gqa6(
    const uint16_t *query, float *score, uint32_t tile_tokens,
    size_t q_row_stride_bytes);
extern void akv_v2_compute_scores_f16_d128_gqa6_q2(
    const uint16_t *query0, const uint16_t *query1, float *score,
    uint32_t tile_tokens);
extern void akv_v2_compute_scores_f16_d128_gqa6_q2_panel4(
    const uint16_t *query0, const uint16_t *query1, float *score,
    uint32_t tile_tokens);
extern void akv_v2_update_outputs_f16_d128_gqa6(
    const float *score, uint16_t *accumulator, const float *old_scale,
    uint32_t tile_tokens);
extern void akv_v2_compute_scores_f16_generic(
    const uint16_t *query, float *score, uint32_t tile_tokens,
    size_t q_row_stride_bytes, uint32_t q_rows, uint32_t head_dim);
extern void akv_v2_update_outputs_f16_generic(
    const float *score, uint16_t *accumulator, const float *old_scale,
    uint32_t tile_tokens, uint32_t q_rows, uint32_t head_dim);
extern void akv_v2_update_outputs_f32_d128_gqa6(
    const float *score, float *accumulator, const float *old_scale,
    uint32_t tile_tokens);
extern void akv_v2_update_outputs_f32_generic(
    const float *score, float *accumulator, const float *old_scale,
    uint32_t tile_tokens, uint32_t q_rows, uint32_t head_dim);
extern void akv_v2_compute_scores_f16_d256_generic(
    const uint16_t *query, float *score, uint32_t tile_tokens,
    size_t q_row_stride_bytes, uint32_t q_rows);
extern void akv_v2_update_outputs_f16_d256_generic(
    const float *score, uint16_t *accumulator, const float *old_scale,
    uint32_t tile_tokens, uint32_t q_rows);

static inline float negative_infinity_f32(void) {
  const uint32_t bits = UINT32_C(0xff800000);
  float value;
  memcpy(&value, &bits, sizeof(value));
  return value;
}

static inline vfloat32m2_t vector_expf(vfloat32m2_t x, size_t vl) {
  // The exponent-bit approximation below only represents normal F32 values.
  // Softmax terms below ln(FLT_MIN) are negligible; clamp them while forming
  // the approximation and explicitly return zero to avoid exponent wraparound.
  const float minimum_normal_log = -0x1.5d58ap+6f;
  const vbool16_t underflow =
      __riscv_vmflt_vf_f32m2_b16(x, minimum_normal_log, vl);
  x = __riscv_vfmax_vf_f32m2(x, minimum_normal_log, vl);
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
  const vfloat32m2_t result = __riscv_vfmacc_vv_f32m2(k, j, k, vl);
  return __riscv_vfmerge_vfm_f32m2(result, 0.0f, underflow, vl);
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

static void convert_prefill_query_block(
    const akv_attention_v2_prefill_problem_t *problem,
    const akv_attention_v2_prefill_layout_t *layout,
    akv_attention_v2_prefill_workspace_t *workspace, uint32_t first_qhead,
    uint32_t token_start, uint32_t token_count, uint32_t q_rows) {
#pragma clang loop unroll(disable)
  for (uint32_t local_token = 0u; local_token < token_count; ++local_token) {
#pragma clang loop unroll(disable)
    for (uint32_t head = 0u; head < q_rows; ++head) {
      const uint32_t token = token_start + local_token;
      const float *const source = (const float *)(const void *)(
          (const char *)problem->query +
          (size_t)(first_qhead + head) * layout->query_head_stride_bytes +
          (size_t)token * layout->query_token_stride_bytes);
      uint16_t *const destination = workspace->query[local_token][head];
      uint32_t offset = 0u;
      while (offset < problem->head_dim) {
        const size_t vl =
            __riscv_vsetvl_e32m4(problem->head_dim - offset);
        const vfloat32m4_t values =
            __riscv_vle32_v_f32m4(source + offset, vl);
        __riscv_vse16_v_f16m2(
            (_Float16 *)destination + offset,
            __riscv_vfncvt_f_f_w_f16m2(values, vl), vl);
        offset += (uint32_t)vl;
      }
    }
  }
}

static void initialize_prefill_block(
    const akv_attention_v2_prefill_problem_t *problem,
    const akv_attention_v2_prefill_layout_t *layout,
    akv_attention_v2_prefill_workspace_t *workspace, uint32_t first_qhead,
    uint32_t token_start, uint32_t token_count, uint32_t q_rows) {
  const float negative_infinity = negative_infinity_f32();
  for (uint32_t local_token = 0u; local_token < token_count; ++local_token) {
    for (uint32_t head = 0u; head < q_rows; ++head) {
      workspace->maximum[local_token][head] = negative_infinity;
      workspace->sum[local_token][head] = 0.0f;
      float *const output = (float *)(void *)(
          (char *)problem->output +
          (size_t)(token_start + local_token) *
              layout->output_token_stride_bytes +
          (size_t)(first_qhead + head) * problem->head_dim * sizeof(float));
      uint32_t offset = 0u;
      while (offset < problem->head_dim) {
        const size_t vl =
            __riscv_vsetvl_e32m4(problem->head_dim - offset);
        __riscv_vse32_v_f32m4(
            output + offset, __riscv_vfmv_v_f_f32m4(0.0f, vl), vl);
        offset += (uint32_t)vl;
      }
    }
  }
}

static inline __attribute__((always_inline)) void
convert_prefill_query_row_d128(const float *source, uint16_t *destination,
                               size_t vl) {
  const vfloat32m4_t values = __riscv_vle32_v_f32m4(source, vl);
  __riscv_vse16_v_f16m2(
      (_Float16 *)destination,
      __riscv_vfncvt_f_f_w_f16m2(values, vl), vl);
}

static void prepare_prefill_block_d128_gqa6(
    const akv_attention_v2_prefill_problem_t *problem,
    const akv_attention_v2_prefill_layout_t *layout,
    akv_attention_v2_prefill_workspace_t *workspace, uint32_t first_qhead,
    uint32_t token_start, uint32_t token_count) {
  const size_t query_vl = __riscv_vsetvl_e32m4(AKV_HEAD_DIM_128);
  const size_t output_vl = __riscv_vsetvl_e32m8(2u * AKV_HEAD_DIM_128);
  const size_t query_head_stride =
      layout->query_head_stride_bytes / sizeof(float);
  const size_t query_token_stride =
      layout->query_token_stride_bytes / sizeof(float);
  const size_t output_token_stride =
      layout->output_token_stride_bytes / sizeof(float);
  const float negative_infinity = negative_infinity_f32();

  const float *source0 = problem->query +
      (size_t)(first_qhead + 0u) * query_head_stride +
      (size_t)token_start * query_token_stride;
  const float *source1 = source0 + query_head_stride;
  const float *source2 = source1 + query_head_stride;
  const float *source3 = source2 + query_head_stride;
  const float *source4 = source3 + query_head_stride;
  const float *source5 = source4 + query_head_stride;
  float *output = problem->output +
      (size_t)token_start * output_token_stride +
      (size_t)first_qhead * AKV_HEAD_DIM_128;

  for (uint32_t local_token = 0u; local_token < token_count; ++local_token) {
    convert_prefill_query_row_d128(
        source0, workspace->query[local_token][0], query_vl);
    convert_prefill_query_row_d128(
        source1, workspace->query[local_token][1], query_vl);
    convert_prefill_query_row_d128(
        source2, workspace->query[local_token][2], query_vl);
    convert_prefill_query_row_d128(
        source3, workspace->query[local_token][3], query_vl);
    convert_prefill_query_row_d128(
        source4, workspace->query[local_token][4], query_vl);
    convert_prefill_query_row_d128(
        source5, workspace->query[local_token][5], query_vl);

    const vfloat32m8_t zero = __riscv_vfmv_v_f_f32m8(0.0f, output_vl);
    __riscv_vse32_v_f32m8(output, zero, output_vl);
    __riscv_vse32_v_f32m8(output + 2u * AKV_HEAD_DIM_128, zero, output_vl);
    __riscv_vse32_v_f32m8(output + 4u * AKV_HEAD_DIM_128, zero, output_vl);

    for (uint32_t head = 0u; head < AKV_ATTENTION_KERNEL_Q_ROWS; ++head) {
      workspace->maximum[local_token][head] = negative_infinity;
      workspace->sum[local_token][head] = 0.0f;
    }

    source0 += query_token_stride;
    source1 += query_token_stride;
    source2 += query_token_stride;
    source3 += query_token_stride;
    source4 += query_token_stride;
    source5 += query_token_stride;
    output += output_token_stride;
  }
}

static __attribute__((noinline)) void apply_prefill_scale_mask_softmax(
    const uint16_t *mask_bits, float scale,
    akv_attention_v2_prefill_workspace_t *workspace, uint32_t local_token,
    uint32_t compute_slot, uint32_t tile_tokens, uint32_t q_rows) {
  const size_t vl = __riscv_vsetvl_e32m2(tile_tokens);
  const vfloat32m2_t mask = __riscv_vfwcvt_f_f_v_f32m2(
      __riscv_vle16_v_f16m1((const _Float16 *)mask_bits, vl), vl);

#pragma clang loop unroll(disable)
  for (uint32_t head = 0u; head < q_rows; ++head) {
    vfloat32m2_t score =
        __riscv_vle32_v_f32m2(workspace->score[compute_slot][head], vl);
    score = __riscv_vfadd_vv_f32m2(
        __riscv_vfmul_vf_f32m2(score, scale, vl), mask, vl);
    const float tile_maximum = reduce_max_f32m2(score, vl);
    const float old_maximum = workspace->maximum[local_token][head];
    const float new_maximum =
        tile_maximum > old_maximum ? tile_maximum : old_maximum;
    const float old_scale = old_maximum == negative_infinity_f32()
                                ? 0.0f
                                : __builtin_expf(old_maximum - new_maximum);
    score = vector_expf(
        __riscv_vfsub_vf_f32m2(score, new_maximum, vl), vl);
    workspace->sum[local_token][head] =
        workspace->sum[local_token][head] * old_scale +
        reduce_sum_f32m2(score, vl);
    workspace->maximum[local_token][head] = new_maximum;
    workspace->old_scale[compute_slot][head] = old_scale;
    __riscv_vse32_v_f32m2(
        workspace->score[compute_slot][head], score, vl);
  }
}

static void normalize_prefill_block(
    const akv_attention_v2_prefill_problem_t *problem,
    const akv_attention_v2_prefill_layout_t *layout,
    const akv_attention_v2_prefill_workspace_t *workspace,
    uint32_t first_qhead, uint32_t token_start, uint32_t token_count,
    uint32_t q_rows) {
  for (uint32_t local_token = 0u; local_token < token_count; ++local_token) {
    for (uint32_t head = 0u; head < q_rows; ++head) {
      const float sum = workspace->sum[local_token][head];
      const float inverse = sum == 0.0f ? 0.0f : 1.0f / sum;
      float *const output = (float *)(void *)(
          (char *)problem->output +
          (size_t)(token_start + local_token) *
              layout->output_token_stride_bytes +
          (size_t)(first_qhead + head) * problem->head_dim * sizeof(float));
      uint32_t offset = 0u;
      while (offset < problem->head_dim) {
        const size_t vl =
            __riscv_vsetvl_e32m4(problem->head_dim - offset);
        const vfloat32m4_t values =
            __riscv_vle32_v_f32m4(output + offset, vl);
        __riscv_vse32_v_f32m4(
            output + offset,
            __riscv_vfmul_vf_f32m4(values, inverse, vl), vl);
        offset += (uint32_t)vl;
      }
    }
  }
}

static void initialize_workspace(akv_attention_v2_workspace_t *workspace,
                                 uint32_t q_rows, uint32_t head_dim) {
  const float negative_infinity = negative_infinity_f32();
#pragma clang loop unroll(disable)
  for (uint32_t head = 0; head < q_rows; ++head) {
    size_t offset = 0;
    while (offset < head_dim) {
      const size_t vl = __riscv_vsetvl_e16m2(head_dim - offset);
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
    uint32_t tile_tokens, uint32_t q_rows) {
  const size_t vl = __riscv_vsetvl_e32m2(tile_tokens);
  const vfloat32m2_t mask = __riscv_vfwcvt_f_f_v_f32m2(
      __riscv_vle16_v_f16m1(
          (const _Float16 *)mask_bits + tile_start, vl),
      vl);

#pragma clang loop unroll(disable)
  for (uint32_t head = 0; head < q_rows; ++head) {
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
    const akv_attention_v2_workspace_t *workspace, uint32_t q_rows,
    uint32_t head_dim) {
#pragma clang loop unroll(disable)
  for (uint32_t head = 0; head < q_rows; ++head) {
    const float inverse =
        workspace->sum[head] == 0.0f ? 0.0f : 1.0f / workspace->sum[head];
    float *output = (float *)((uint8_t *)output_base +
                             head * output_row_stride_bytes);
    size_t offset = 0;
    while (offset < head_dim) {
      const size_t vl = __riscv_vsetvl_e16m2(head_dim - offset);
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

static __attribute__((noinline)) akv_status_t execute_segmented_d256(
    const akv_attention_plan_t *plan,
    akv_attention_v2_workspace_t *workspace) {
  const uint16_t *const query =
      (const uint16_t *)(uintptr_t)(
          plan->descriptor.q_base -
          (uint64_t)plan->d_offset * sizeof(uint16_t));
  const uint16_t *const mask_bits = plan->mask;
  float *const output = plan->output;
  const uint32_t query_row_stride_bytes =
      plan->descriptor.q_row_stride_bytes;
  const uint32_t q_rows = plan->descriptor.q_rows;
  const uint32_t head_dim = plan->logical_head_dim;
  const uint32_t kv_length = plan->descriptor.kv_length;
  const size_t output_row_stride_bytes = plan->output_row_stride_bytes;
  const float scale = plan->scale;

  initialize_workspace(workspace, q_rows, head_dim);
  for (uint32_t tile_start = 0; tile_start < kv_length;
       tile_start += AKV_V2_TILE_TOKENS) {
    const uint32_t tile_tokens =
        akv_v2_tile_length(kv_length, tile_start);
    issue_full(&plan->descriptor, tile_start);
    akv_v2_compute_scores_f16_d256_generic(
        query, &workspace->score[0][0], tile_tokens,
        query_row_stride_bytes, q_rows);
    apply_scale_mask_and_softmax(mask_bits, scale, workspace, tile_start,
                                 tile_tokens, q_rows);
    issue_full(&plan->value_descriptor, tile_start);
    akv_v2_update_outputs_f16_d256_generic(
        &workspace->score[0][0], &workspace->accumulator[0][0],
        workspace->old_scale, tile_tokens, q_rows);
  }
  issue_release();
  store_outputs(output, output_row_stride_bytes, workspace, q_rows, head_dim);
  return AKV_STATUS_OK;
}
#endif

akv_status_t akv_attention_execute_v2_native(
    const akv_attention_plan_t *plan,
    akv_attention_v2_workspace_t *workspace) {
  const int segmented_d256 =
      plan != NULL && plan->d_segment_count == 2u;
  if (workspace == NULL ||
      (segmented_d256 ? !akv_attention_plan_v2_is_valid(plan)
                      : !common_v2_plan_is_valid(plan)) ||
      ((uintptr_t)workspace & (AKV_DESCRIPTOR_BYTES - 1u)) != 0u)
    return AKV_STATUS_BAD_ARGUMENT;

#if defined(__riscv) && __riscv_xlen == 64 && defined(__riscv_vector) &&       \
    defined(__riscv_zvfh) && !defined(SPIKE)
  if (segmented_d256)
    return execute_segmented_d256(plan, workspace);

  // AKV commands cross into a non-scalar memory client.  Snapshot every field
  // consumed by the following software schedule before issuing the first
  // command, so the schedule never depends on re-reading the DMA descriptor.
  const uint16_t *const query =
      (const uint16_t *)(uintptr_t)plan->descriptor.q_base;
  const uint16_t *const mask_bits = plan->mask;
  float *const output = plan->output;
  const uint32_t query_row_stride_bytes =
      plan->descriptor.q_row_stride_bytes;
  const uint32_t q_rows = plan->descriptor.q_rows;
  const uint32_t head_dim = plan->descriptor.head_dim;
  const uint32_t kv_length = plan->descriptor.kv_length;
  const size_t output_row_stride_bytes = plan->output_row_stride_bytes;
  const float scale = plan->scale;

  initialize_workspace(workspace, q_rows, head_dim);
  for (uint32_t tile_start = 0; tile_start < kv_length;
       tile_start += AKV_V2_TILE_TOKENS) {
    const uint32_t tile_tokens =
        akv_v2_tile_length(kv_length, tile_start);
    if (tile_start == 0u)
      issue_full(&plan->descriptor, 0u);
    else
      issue_refill(tile_start);

    if (q_rows == AKV_ATTENTION_KERNEL_Q_ROWS &&
        head_dim == AKV_HEAD_DIM_128) {
      akv_v2_compute_scores_f16_d128_gqa6(
          query, &workspace->score[0][0], tile_tokens,
          query_row_stride_bytes);
    } else {
      akv_v2_compute_scores_f16_generic(
          query, &workspace->score[0][0], tile_tokens,
          query_row_stride_bytes, q_rows, head_dim);
    }
    apply_scale_mask_and_softmax(mask_bits, scale, workspace, tile_start,
                                 tile_tokens, q_rows);
    if (q_rows == AKV_ATTENTION_KERNEL_Q_ROWS &&
        head_dim == AKV_HEAD_DIM_128) {
      akv_v2_update_outputs_f16_d128_gqa6(
          &workspace->score[0][0], &workspace->accumulator[0][0],
          workspace->old_scale, tile_tokens);
    } else {
      akv_v2_update_outputs_f16_generic(
          &workspace->score[0][0], &workspace->accumulator[0][0],
          workspace->old_scale, tile_tokens, q_rows, head_dim);
    }
  }
  issue_release();
  store_outputs(output, output_row_stride_bytes, workspace, q_rows, head_dim);
  return AKV_STATUS_OK;
#else
  return AKV_STATUS_RUNTIME_UNAVAILABLE;
#endif
}

akv_status_t akv_attention_execute_v2_prefill_native(
    const akv_device_t *device,
    const akv_attention_v2_prefill_problem_t *problem,
    akv_attention_v2_prefill_workspace_t *workspace) {
  uint32_t past_tokens = 0u;
  uint32_t maximum_prefix = 0u;
  akv_attention_v2_prefill_layout_t layout;
  const akv_status_t validation = akv_attention_v2_prefill_validate(
      device, problem, workspace, &past_tokens, &maximum_prefix, &layout);
  if (validation != AKV_STATUS_OK) return validation;

#if defined(__riscv) && __riscv_xlen == 64 && defined(__riscv_vector) &&       \
    defined(__riscv_zvfh) && !defined(SPIKE)
  const uint32_t q_rows = problem->query_heads / problem->kv_heads;
  const uint32_t query_stride_bytes = sizeof(workspace->query[0][0]);
  const uint32_t output_stride_bytes = problem->head_dim * sizeof(float);

  /* Preflight every bounded block before touching architectural output. */
  for (uint32_t kv_head = 0u; kv_head < problem->kv_heads; ++kv_head) {
    const uint32_t first_qhead = kv_head * q_rows;
    for (uint32_t token_start = 0u; token_start < problem->query_tokens;
         token_start += AKV_PREFILL_QUERY_BLOCK_TOKENS) {
      uint32_t token_count = problem->query_tokens - token_start;
      if (token_count > AKV_PREFILL_QUERY_BLOCK_TOKENS)
        token_count = AKV_PREFILL_QUERY_BLOCK_TOKENS;
      const uint32_t block_prefix = past_tokens + token_start + token_count;
      const akv_attention_problem_t context_problem = {
          .query = &workspace->query[0][0][0],
          .key = (const uint16_t *)(const void *)(
              (const char *)problem->key +
              (size_t)kv_head * layout.key_head_stride_bytes),
          .value = (const uint16_t *)(const void *)(
              (const char *)problem->value +
              (size_t)kv_head * layout.value_head_stride_bytes),
          .mask = (const uint16_t *)(const void *)(
              (const char *)problem->mask +
              (size_t)token_start * layout.mask_token_stride_bytes),
          .output = (float *)(void *)(
              (char *)problem->output +
              (size_t)token_start * layout.output_token_stride_bytes +
              (size_t)first_qhead * output_stride_bytes),
          .q_row_stride_bytes = query_stride_bytes,
          .k_token_stride_bytes = layout.key_token_stride_bytes,
          .v_token_stride_bytes = layout.value_token_stride_bytes,
          .output_row_stride_bytes = output_stride_bytes,
          .q_rows = q_rows,
          .head_dim = problem->head_dim,
          .kv_length = block_prefix,
          .scale = problem->scale,
      };
      const akv_status_t plan_status = akv_attention_plan_create_v2(
          device, &context_problem, &workspace->plan);
      if (plan_status != AKV_STATUS_OK) return plan_status;
    }
  }

  for (uint32_t kv_head = 0u; kv_head < problem->kv_heads; ++kv_head) {
    const uint32_t first_qhead = kv_head * q_rows;
    for (uint32_t token_start = 0u; token_start < problem->query_tokens;
         token_start += AKV_PREFILL_QUERY_BLOCK_TOKENS) {
      uint32_t token_count = problem->query_tokens - token_start;
      if (token_count > AKV_PREFILL_QUERY_BLOCK_TOKENS)
        token_count = AKV_PREFILL_QUERY_BLOCK_TOKENS;
      const uint32_t block_prefix = past_tokens + token_start + token_count;

      AKV_PROFILE_PHASE(AKV_PROFILE_PHASE_QUERY);
      if (q_rows == AKV_ATTENTION_KERNEL_Q_ROWS &&
          problem->head_dim == AKV_HEAD_DIM_128 &&
          __riscv_vsetvl_e32m4(AKV_HEAD_DIM_128) == AKV_HEAD_DIM_128 &&
          __riscv_vsetvl_e32m8(2u * AKV_HEAD_DIM_128) ==
              2u * AKV_HEAD_DIM_128) {
        prepare_prefill_block_d128_gqa6(
            problem, &layout, workspace, first_qhead, token_start, token_count);
      } else {
        convert_prefill_query_block(problem, &layout, workspace, first_qhead,
                                    token_start, token_count, q_rows);
        initialize_prefill_block(problem, &layout, workspace, first_qhead,
                                 token_start, token_count, q_rows);
      }

      const akv_attention_problem_t context_problem = {
          .query = &workspace->query[0][0][0],
          .key = (const uint16_t *)(const void *)(
              (const char *)problem->key +
              (size_t)kv_head * layout.key_head_stride_bytes),
          .value = (const uint16_t *)(const void *)(
              (const char *)problem->value +
              (size_t)kv_head * layout.value_head_stride_bytes),
          .mask = (const uint16_t *)(const void *)(
              (const char *)problem->mask +
              (size_t)token_start * layout.mask_token_stride_bytes),
          .output = (float *)(void *)(
              (char *)problem->output +
              (size_t)token_start * layout.output_token_stride_bytes +
              (size_t)first_qhead * output_stride_bytes),
          .q_row_stride_bytes = query_stride_bytes,
          .k_token_stride_bytes = layout.key_token_stride_bytes,
          .v_token_stride_bytes = layout.value_token_stride_bytes,
          .output_row_stride_bytes = output_stride_bytes,
          .q_rows = q_rows,
          .head_dim = problem->head_dim,
          .kv_length = block_prefix,
          .scale = problem->scale,
      };
      const akv_status_t plan_status = akv_attention_plan_create_v2(
          device, &context_problem, &workspace->plan);
      if (plan_status != AKV_STATUS_OK) return AKV_STATUS_EXECUTION;

      for (uint32_t tile_start = 0u; tile_start < block_prefix;
           tile_start += AKV_V2_TILE_TOKENS) {
        AKV_PROFILE_PHASE(AKV_PROFILE_PHASE_KV);
        if (tile_start == 0u)
          issue_full(&workspace->plan.descriptor, 0u);
        else
          issue_refill(tile_start);

        const uint32_t resident_tokens =
            akv_v2_tile_length(block_prefix, tile_start);
        AKV_PROFILE_PHASE(AKV_PROFILE_PHASE_COMPUTE);
        const int d128_gqa6 =
            q_rows == AKV_ATTENTION_KERNEL_Q_ROWS &&
            problem->head_dim == AKV_HEAD_DIM_128;
        for (uint32_t local_token = 0u; local_token < token_count;) {
          uint32_t compute_tokens = 1u;
          if (d128_gqa6 && local_token + 1u < token_count)
            compute_tokens = AKV_PREFILL_COMPUTE_TILE_TOKENS;

          uint32_t visible_tokens[AKV_PREFILL_COMPUTE_TILE_TOKENS] = {0u, 0u};
          for (uint32_t compute_slot = 0u;
               compute_slot < compute_tokens; ++compute_slot) {
            const uint32_t token =
                token_start + local_token + compute_slot;
            const uint32_t active_prefix = past_tokens + token + 1u;
            if (active_prefix > tile_start) {
              visible_tokens[compute_slot] = active_prefix - tile_start;
              if (visible_tokens[compute_slot] > resident_tokens)
                visible_tokens[compute_slot] = resident_tokens;
            }
          }

          const int use_q2 = compute_tokens == 2u &&
                             visible_tokens[0] != 0u &&
                             visible_tokens[1] != 0u;
          if (use_q2) {
            if (device->capabilities.token_axis_column_panel4) {
              akv_v2_compute_scores_f16_d128_gqa6_q2_panel4(
                  &workspace->query[local_token][0][0],
                  &workspace->query[local_token + 1u][0][0],
                  &workspace->score[0][0][0], visible_tokens[1]);
            } else {
              akv_v2_compute_scores_f16_d128_gqa6_q2(
                  &workspace->query[local_token][0][0],
                  &workspace->query[local_token + 1u][0][0],
                  &workspace->score[0][0][0], visible_tokens[1]);
            }
          }

          for (uint32_t compute_slot = 0u;
               compute_slot < compute_tokens; ++compute_slot) {
            const uint32_t active_tokens = visible_tokens[compute_slot];
            if (active_tokens == 0u) continue;
            const uint32_t token =
                token_start + local_token + compute_slot;

            if (!use_q2) {
              const uint16_t *const query =
                  &workspace->query[local_token + compute_slot][0][0];
              if (d128_gqa6) {
                akv_v2_compute_scores_f16_d128_gqa6(
                    query, &workspace->score[compute_slot][0][0],
                    active_tokens, query_stride_bytes);
              } else {
                akv_v2_compute_scores_f16_generic(
                    query, &workspace->score[compute_slot][0][0],
                    active_tokens, query_stride_bytes, q_rows,
                    problem->head_dim);
              }
            }

            const uint16_t *const tile_mask =
                (const uint16_t *)(const void *)(
                    (const char *)problem->mask +
                    (size_t)token * layout.mask_token_stride_bytes) +
                tile_start;
            apply_prefill_scale_mask_softmax(
                tile_mask, problem->scale, workspace,
                local_token + compute_slot, compute_slot, active_tokens,
                q_rows);

            float *const output = (float *)(void *)(
                (char *)problem->output +
                (size_t)token * layout.output_token_stride_bytes +
                (size_t)first_qhead * output_stride_bytes);
            if (d128_gqa6) {
              akv_v2_update_outputs_f32_d128_gqa6(
                  &workspace->score[compute_slot][0][0], output,
                  workspace->old_scale[compute_slot], active_tokens);
            } else {
              akv_v2_update_outputs_f32_generic(
                  &workspace->score[compute_slot][0][0], output,
                  workspace->old_scale[compute_slot], active_tokens, q_rows,
                  problem->head_dim);
            }
          }
          local_token += compute_tokens;
        }
      }
      issue_release();
      normalize_prefill_block(problem, &layout, workspace, first_qhead,
                              token_start, token_count, q_rows);
    }
  }
  return AKV_STATUS_OK;
#else
  (void)past_tokens;
  (void)maximum_prefix;
  return AKV_STATUS_RUNTIME_UNAVAILABLE;
#endif
}
