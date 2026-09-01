#include "../include/akv/akv.h"

#include <limits.h>
#include <string.h>

const char *akv_status_string(akv_status_t status) {
  switch (status) {
  case AKV_STATUS_OK:
    return "ok";
  case AKV_STATUS_BAD_ARGUMENT:
    return "bad_argument";
  case AKV_STATUS_RUNTIME_UNAVAILABLE:
    return "runtime_unavailable";
  case AKV_STATUS_ABI_MISMATCH:
    return "abi_mismatch";
  case AKV_STATUS_CAPABILITY:
    return "capability";
  case AKV_STATUS_SHAPE:
    return "shape";
  case AKV_STATUS_LAYOUT:
    return "layout";
  case AKV_STATUS_RANGE:
    return "range";
  case AKV_STATUS_ALIAS:
    return "alias";
  case AKV_STATUS_EXECUTION:
    return "execution";
  }
  return "unknown";
}

akv_status_t akv_capabilities_decode(uint64_t info0, uint64_t info1,
                                     akv_capabilities_t *capabilities) {
  if (capabilities == NULL)
    return AKV_STATUS_BAD_ARGUMENT;
  memset(capabilities, 0, sizeof(*capabilities));
  if (info0 == 0u || info1 == 0u)
    return AKV_STATUS_RUNTIME_UNAVAILABLE;

  capabilities->architecture_version = (uint8_t)(info0 & 0xffu);
  capabilities->descriptor_version = (uint8_t)((info0 >> 8) & 0xffu);
  capabilities->descriptor_bytes = (uint8_t)((info0 >> 16) & 0xffu);
  capabilities->max_q_rows = (uint8_t)((info0 >> 24) & 0xffu);
  capabilities->tile_tokens = (uint8_t)((info0 >> 32) & 0xffu);
  capabilities->context_count = (uint8_t)((info0 >> 40) & 0xffu);
  capabilities->enabled = (uint8_t)((info0 >> 48) & 1u);
  capabilities->f16_payload = (uint8_t)((info0 >> 49) & 1u);
  capabilities->head_dim_64 = (uint8_t)((info0 >> 50) & 1u);
  capabilities->head_dim_128 = (uint8_t)((info0 >> 51) & 1u);
  capabilities->descriptor_alignment_log2 = (uint8_t)((info1 >> 20) & 0xffu);

  if (capabilities->architecture_version != AKV_ARCHITECTURE_VERSION ||
      capabilities->descriptor_version != AKV_DESCRIPTOR_VERSION ||
      capabilities->descriptor_bytes != AKV_DESCRIPTOR_BYTES ||
      capabilities->descriptor_alignment_log2 !=
          AKV_DESCRIPTOR_ALIGNMENT_LOG2 ||
      capabilities->max_q_rows == 0u ||
      capabilities->max_q_rows > AKV_MAX_Q_ROWS ||
      capabilities->tile_tokens != AKV_TILE_TOKENS ||
      capabilities->context_count == 0u ||
      capabilities->context_count > AKV_CONTEXT_COUNT || (info0 >> 52) != 0u ||
      info1 != akv_capability_word(1u, 1))
    return AKV_STATUS_ABI_MISMATCH;
  if (!capabilities->enabled)
    return AKV_STATUS_RUNTIME_UNAVAILABLE;

  capabilities->valid = 1u;
  return AKV_STATUS_OK;
}

akv_status_t akv_capabilities_decode_extended(
    uint64_t info0, uint64_t info1, uint64_t info2, uint64_t info3,
    akv_capabilities_t *capabilities) {
  const akv_status_t base_status =
      akv_capabilities_decode(info0, info1, capabilities);
  if (base_status != AKV_STATUS_OK)
    return base_status;

  if (info2 == 0u && info3 == 0u)
    return AKV_STATUS_OK;
  if (info2 == 0u || info3 == 0u)
    return AKV_STATUS_ABI_MISMATCH;

  capabilities->token_axis_profile_version = (uint8_t)(info2 & 0xffu);
  capabilities->token_axis_tile_tokens = (uint8_t)((info2 >> 8) & 0xffu);
  capabilities->token_axis_banks = (uint8_t)((info2 >> 16) & 0xffu);
  capabilities->token_axis_selector_index_bits =
      (uint8_t)((info2 >> 24) & 0xffu);
  capabilities->token_axis_enabled = (uint8_t)((info2 >> 32) & 1u);
  capabilities->token_axis_tail = (uint8_t)((info2 >> 35) & 1u);
  capabilities->token_axis_row_view = (uint8_t)((info2 >> 36) & 1u);
  capabilities->token_axis_d_axis_tail =
      (uint8_t)((info2 >> AKV_V2_D_AXIS_TAIL_CAPABILITY_BIT) & 1u);
  capabilities->token_axis_d256_segmented =
      (uint8_t)((info2 >> AKV_V2_D256_SEGMENTED_CAPABILITY_BIT) & 1u);

  const uint64_t optional_capability_bits =
      (UINT64_C(1) << AKV_V2_D_AXIS_TAIL_CAPABILITY_BIT) |
      (UINT64_C(1) << AKV_V2_D256_SEGMENTED_CAPABILITY_BIT);
  const uint64_t expected_info2 = akv_v2_capability_word(
      2u, capabilities->token_axis_enabled != 0u);
  if ((info2 & ~optional_capability_bits) !=
          (expected_info2 & ~optional_capability_bits) ||
      info3 != akv_v2_capability_word(3u, 1) ||
      capabilities->token_axis_profile_version != AKV_V2_PROFILE_VERSION ||
      capabilities->token_axis_tile_tokens != AKV_V2_TILE_TOKENS ||
      capabilities->token_axis_banks != AKV_V2_TOKEN_BANKS ||
      capabilities->token_axis_selector_index_bits !=
          AKV_V2_SELECTOR_INDEX_BITS)
    return AKV_STATUS_ABI_MISMATCH;

  capabilities->token_axis_valid = capabilities->token_axis_enabled;
  return AKV_STATUS_OK;
}

akv_status_t akv_device_query(akv_info_reader_t reader, void *context,
                              akv_device_t *device) {
  if (reader == NULL || device == NULL)
    return AKV_STATUS_BAD_ARGUMENT;
  memset(device, 0, sizeof(*device));
  return akv_capabilities_decode_extended(
      reader(context, 0u), reader(context, 1u), reader(context, 2u),
      reader(context, 3u), &device->capabilities);
}

static uint64_t reference_info(void *context, unsigned index) {
  (void)context;
  const uint64_t base = akv_capability_word(index, 1);
  return base != 0u ? base : akv_v2_capability_word(index, 1);
}

akv_status_t akv_device_init_reference(akv_device_t *device) {
  return akv_device_query(reference_info, NULL, device);
}

static int finite_positive_f32(float value) {
  uint32_t bits;
  memcpy(&bits, &value, sizeof(bits));
  return (bits >> 31) == 0u && (bits & UINT32_C(0x7fffffff)) != 0u &&
         (bits & UINT32_C(0x7f800000)) != UINT32_C(0x7f800000);
}

static int range_fits(uintptr_t base, size_t stride, size_t count,
                      size_t row_bytes, uintptr_t *last_byte) {
  if (base == 0u || count == 0u || row_bytes == 0u)
    return 0;
  size_t row_offset;
  uintptr_t last_row;
  if (__builtin_mul_overflow(count - 1u, stride, &row_offset) ||
      __builtin_add_overflow(base, row_offset, &last_row) ||
      __builtin_add_overflow(last_row, row_bytes - 1u, last_byte))
    return 0;
  return 1;
}

static int ranges_overlap(uintptr_t lhs_first, uintptr_t lhs_last,
                          uintptr_t rhs_first, uintptr_t rhs_last) {
  return lhs_first <= rhs_last && rhs_first <= lhs_last;
}

int akv_attention_v2_shape_supported(uint32_t q_rows, uint32_t head_dim) {
  return q_rows >= 1u && q_rows <= AKV_MAX_Q_ROWS &&
         (head_dim == AKV_HEAD_DIM_64 || head_dim == AKV_HEAD_DIM_96 ||
          head_dim == AKV_HEAD_DIM_128 || head_dim == AKV_HEAD_DIM_256);
}

int akv_attention_plan_v2_is_valid(const akv_attention_plan_t *plan) {
  if (plan == NULL || plan->kernel_version != AKV_ATTENTION_KERNEL_VERSION_V2 ||
      plan->mask == NULL || plan->output == NULL ||
      !finite_positive_f32(plan->scale) || plan->reserved[0] != 0u)
    return 0;

  if (plan->d_segment_count == 1u) {
    return plan->d_offset == 0u &&
           plan->d_count == plan->descriptor.head_dim &&
           plan->logical_head_dim == plan->descriptor.head_dim &&
           akv_attention_v2_shape_supported(plan->descriptor.q_rows,
                                            plan->logical_head_dim) &&
           akv_v2_descriptor_is_valid(&plan->descriptor) &&
           plan->output_row_stride_bytes >=
               (size_t)plan->logical_head_dim * sizeof(float);
  }

  if (plan->d_segment_count != 2u ||
      plan->logical_head_dim != AKV_HEAD_DIM_256 || plan->d_offset != 0u ||
      plan->d_count != AKV_HEAD_DIM_128 ||
      !akv_v2_descriptor_is_valid(&plan->descriptor) ||
      !akv_v2_descriptor_is_valid(&plan->value_descriptor))
    return 0;

  const akv_descriptor_t *score = &plan->descriptor;
  const akv_descriptor_t *value = &plan->value_descriptor;
  const uint64_t segment_bytes = (uint64_t)plan->d_count * sizeof(uint16_t);
  const uint32_t logical_row_bytes =
      (uint32_t)plan->logical_head_dim * sizeof(uint16_t);
  return score->head_dim == plan->d_count &&
         value->head_dim == plan->d_count &&
         score->q_rows == value->q_rows &&
         score->kv_length == value->kv_length &&
         score->q_row_stride_bytes == value->q_row_stride_bytes &&
         score->k_token_stride_bytes == score->v_token_stride_bytes &&
         value->k_token_stride_bytes == value->v_token_stride_bytes &&
         score->q_row_stride_bytes >= logical_row_bytes &&
         score->k_token_stride_bytes >= logical_row_bytes &&
         value->k_token_stride_bytes >= logical_row_bytes &&
         score->v_base == score->k_base + segment_bytes &&
         value->q_base == score->q_base + segment_bytes &&
         value->v_base == value->k_base + segment_bytes &&
         plan->output_row_stride_bytes >=
             (size_t)plan->logical_head_dim * sizeof(float);
}

static akv_status_t attention_plan_create(
    const akv_device_t *device, const akv_attention_problem_t *problem,
    uint32_t kernel_version, akv_attention_plan_t *plan) {
  if (device == NULL || problem == NULL || plan == NULL)
    return AKV_STATUS_BAD_ARGUMENT;
  akv_status_t status;

  if (((uintptr_t)plan & (AKV_DESCRIPTOR_BYTES - 1u)) != 0u)
    return AKV_STATUS_LAYOUT;

  const akv_capabilities_t *caps = &device->capabilities;
  if (!caps->valid || !caps->enabled || !caps->f16_payload ||
      caps->context_count == 0u) {
    status = AKV_STATUS_CAPABILITY;
    goto reject;
  }
  if (kernel_version == AKV_ATTENTION_KERNEL_VERSION_V2 &&
      (!caps->token_axis_valid || !caps->token_axis_enabled ||
       !caps->token_axis_tail || !caps->token_axis_row_view)) {
    status = AKV_STATUS_CAPABILITY;
    goto reject;
  }
  if (kernel_version == AKV_ATTENTION_KERNEL_VERSION_V1) {
    if (problem->q_rows != AKV_ATTENTION_KERNEL_Q_ROWS ||
        problem->head_dim != AKV_HEAD_DIM_128) {
      status = AKV_STATUS_SHAPE;
      goto reject;
    }
  } else if (!akv_attention_v2_shape_supported(problem->q_rows,
                                                problem->head_dim)) {
    status = AKV_STATUS_SHAPE;
    goto reject;
  }
  const int head_dim_capable = problem->head_dim == AKV_HEAD_DIM_64
      ? caps->head_dim_64
      : (problem->head_dim == AKV_HEAD_DIM_96
             ? caps->token_axis_d_axis_tail
             : (problem->head_dim == AKV_HEAD_DIM_256
                    ? caps->token_axis_d256_segmented
                    : caps->head_dim_128));
  if (!head_dim_capable || caps->max_q_rows < problem->q_rows) {
    status = AKV_STATUS_CAPABILITY;
    goto reject;
  }
  if (problem->kv_length == 0u || problem->kv_length > UINT16_MAX) {
    status = AKV_STATUS_SHAPE;
    goto reject;
  }
  if (problem->query == NULL || problem->key == NULL ||
      problem->value == NULL || problem->mask == NULL ||
      problem->output == NULL || !finite_positive_f32(problem->scale)) {
    status = AKV_STATUS_BAD_ARGUMENT;
    goto reject;
  }

  const size_t input_row_bytes = (size_t)problem->head_dim * sizeof(uint16_t);
  const size_t output_row_bytes = (size_t)problem->head_dim * sizeof(float);
  if (problem->q_row_stride_bytes < input_row_bytes ||
      problem->k_token_stride_bytes < input_row_bytes ||
      problem->v_token_stride_bytes < input_row_bytes ||
      problem->output_row_stride_bytes < output_row_bytes ||
      problem->q_row_stride_bytes > UINT32_MAX ||
      problem->k_token_stride_bytes > UINT32_MAX ||
      problem->v_token_stride_bytes > UINT32_MAX ||
      ((uintptr_t)problem->query | (uintptr_t)problem->key |
       (uintptr_t)problem->value | (uintptr_t)problem->mask |
       problem->q_row_stride_bytes | problem->k_token_stride_bytes |
       problem->v_token_stride_bytes) &
          (sizeof(uint16_t) - 1u)) {
    status = AKV_STATUS_LAYOUT;
    goto reject;
  }
  if (((uintptr_t)problem->output | problem->output_row_stride_bytes) &
      (sizeof(float) - 1u)) {
    status = AKV_STATUS_LAYOUT;
    goto reject;
  }
  if (kernel_version == AKV_ATTENTION_KERNEL_VERSION_V2 &&
      (((uintptr_t)problem->query | (uintptr_t)problem->key |
        (uintptr_t)problem->value | problem->q_row_stride_bytes |
        problem->k_token_stride_bytes | problem->v_token_stride_bytes) &
       UINT64_C(31)) != 0u) {
    status = AKV_STATUS_LAYOUT;
    goto reject;
  }

  uintptr_t q_last;
  uintptr_t k_last;
  uintptr_t v_last;
  uintptr_t mask_last;
  uintptr_t output_last;
  if (!range_fits((uintptr_t)problem->query, problem->q_row_stride_bytes,
                  problem->q_rows, input_row_bytes, &q_last) ||
      !range_fits((uintptr_t)problem->key, problem->k_token_stride_bytes,
                  problem->kv_length, input_row_bytes, &k_last) ||
      !range_fits((uintptr_t)problem->value, problem->v_token_stride_bytes,
                  problem->kv_length, input_row_bytes, &v_last) ||
      !range_fits((uintptr_t)problem->mask, sizeof(uint16_t),
                  problem->kv_length, sizeof(uint16_t), &mask_last) ||
      !range_fits((uintptr_t)problem->output, problem->output_row_stride_bytes,
                  problem->q_rows, output_row_bytes, &output_last)) {
    status = AKV_STATUS_RANGE;
    goto reject;
  }

  const uintptr_t output_first = (uintptr_t)problem->output;
  if (ranges_overlap(output_first, output_last, (uintptr_t)problem->query,
                     q_last) ||
      ranges_overlap(output_first, output_last, (uintptr_t)problem->key,
                     k_last) ||
      ranges_overlap(output_first, output_last, (uintptr_t)problem->value,
                     v_last) ||
      ranges_overlap(output_first, output_last, (uintptr_t)problem->mask,
                     mask_last)) {
    status = AKV_STATUS_ALIAS;
    goto reject;
  }

  const akv_descriptor_t logical_descriptor = (akv_descriptor_t){
      .version = AKV_DESCRIPTOR_VERSION,
      .element_format = AKV_ELEMENT_FORMAT_F16,
      .q_rows = (uint8_t)problem->q_rows,
      .flags = 0u,
      .head_dim = (uint16_t)problem->head_dim,
      .kv_length = (uint16_t)problem->kv_length,
      .q_row_stride_bytes = (uint32_t)problem->q_row_stride_bytes,
      .k_token_stride_bytes = (uint32_t)problem->k_token_stride_bytes,
      .v_token_stride_bytes = (uint32_t)problem->v_token_stride_bytes,
      .reserved0 = 0u,
      .q_base = (uint64_t)(uintptr_t)problem->query,
      .k_base = (uint64_t)(uintptr_t)problem->key,
      .v_base = (uint64_t)(uintptr_t)problem->value,
      .reserved1 = 0u,
      .reserved2 = 0u,
  };
  plan->descriptor = logical_descriptor;
  plan->mask = problem->mask;
  plan->output = problem->output;
  plan->output_row_stride_bytes = problem->output_row_stride_bytes;
  plan->scale = problem->scale;
  plan->kernel_version = kernel_version;
  plan->logical_head_dim = (uint16_t)problem->head_dim;
  plan->d_offset = 0u;
  plan->d_count = (uint16_t)problem->head_dim;
  plan->d_segment_count = 1u;
  plan->reserved[0] = 0u;

  if (kernel_version == AKV_ATTENTION_KERNEL_VERSION_V2 &&
      problem->head_dim == AKV_HEAD_DIM_256) {
    const uint64_t segment_bytes =
        (uint64_t)AKV_HEAD_DIM_128 * sizeof(uint16_t);
    plan->descriptor.head_dim = AKV_HEAD_DIM_128;
    plan->descriptor.v_base = plan->descriptor.k_base + segment_bytes;
    plan->descriptor.v_token_stride_bytes =
        plan->descriptor.k_token_stride_bytes;
    plan->value_descriptor = plan->descriptor;
    plan->value_descriptor.q_base =
        (uint64_t)(uintptr_t)problem->query + segment_bytes;
    plan->value_descriptor.k_base = (uint64_t)(uintptr_t)problem->value;
    plan->value_descriptor.v_base =
        plan->value_descriptor.k_base + segment_bytes;
    plan->value_descriptor.k_token_stride_bytes =
        (uint32_t)problem->v_token_stride_bytes;
    plan->value_descriptor.v_token_stride_bytes =
        (uint32_t)problem->v_token_stride_bytes;
    plan->d_count = AKV_HEAD_DIM_128;
    plan->d_segment_count = 2u;
  }

  // The common descriptor is constructed solely from fields checked above;
  // the native execution boundary validates it again before issuing hardware
  // commands.  D256 has cross-descriptor relations and therefore retains the
  // full post-construction validation here.
  if (kernel_version == AKV_ATTENTION_KERNEL_VERSION_V2 &&
      problem->head_dim == AKV_HEAD_DIM_256 &&
      !akv_attention_plan_v2_is_valid(plan)) {
    status = AKV_STATUS_LAYOUT;
    goto reject;
  }
  return AKV_STATUS_OK;

reject:
  memset(plan, 0, sizeof(*plan));
  return status;
}

akv_status_t akv_attention_plan_create(const akv_device_t *device,
                                       const akv_attention_problem_t *problem,
                                       akv_attention_plan_t *plan) {
  return attention_plan_create(device, problem,
                               AKV_ATTENTION_KERNEL_VERSION_V1, plan);
}

akv_status_t akv_attention_plan_create_v2(
    const akv_device_t *device, const akv_attention_problem_t *problem,
    akv_attention_plan_t *plan) {
  return attention_plan_create(device, problem,
                               AKV_ATTENTION_KERNEL_VERSION_V2, plan);
}

static akv_status_t attention_execute(const akv_attention_plan_t *plan,
                                      uint32_t kernel_version,
                                      akv_attention_executor_t executor,
                                      void *executor_context) {
  if (plan == NULL || executor == NULL)
    return AKV_STATUS_BAD_ARGUMENT;
  if (plan->kernel_version != kernel_version ||
      (kernel_version == AKV_ATTENTION_KERNEL_VERSION_V2
           ? !akv_attention_plan_v2_is_valid(plan)
           : !akv_descriptor_is_valid(&plan->descriptor)) ||
      plan->mask == NULL ||
      plan->output == NULL ||
      (kernel_version == AKV_ATTENTION_KERNEL_VERSION_V1
           ? (plan->descriptor.q_rows != AKV_ATTENTION_KERNEL_Q_ROWS ||
              plan->descriptor.head_dim != AKV_HEAD_DIM_128)
           : !akv_attention_v2_shape_supported(plan->descriptor.q_rows,
                                               plan->logical_head_dim)) ||
      plan->output_row_stride_bytes <
          (size_t)(kernel_version == AKV_ATTENTION_KERNEL_VERSION_V2
                       ? plan->logical_head_dim
                       : plan->descriptor.head_dim) * sizeof(float) ||
      !finite_positive_f32(plan->scale))
    return AKV_STATUS_BAD_ARGUMENT;

  if (kernel_version == AKV_ATTENTION_KERNEL_VERSION_V2 &&
      plan->d_segment_count == 2u) {
    akv_descriptor_t logical = plan->descriptor;
    logical.head_dim = plan->logical_head_dim;
    logical.q_base -= (uint64_t)plan->d_offset * sizeof(uint16_t);
    logical.k_base -= (uint64_t)plan->d_offset * sizeof(uint16_t);
    logical.v_base = plan->value_descriptor.k_base -
                     (uint64_t)plan->d_offset * sizeof(uint16_t);
    logical.v_token_stride_bytes =
        plan->value_descriptor.k_token_stride_bytes;
    return executor(executor_context, &logical, plan->mask, plan->output,
                    plan->output_row_stride_bytes, plan->scale);
  }
  return executor(executor_context, &plan->descriptor, plan->mask, plan->output,
                  plan->output_row_stride_bytes, plan->scale);
}

akv_status_t akv_attention_execute(const akv_attention_plan_t *plan,
                                   akv_attention_executor_t executor,
                                   void *executor_context) {
  return attention_execute(plan, AKV_ATTENTION_KERNEL_VERSION_V1, executor,
                           executor_context);
}

akv_status_t akv_attention_execute_v2(const akv_attention_plan_t *plan,
                                      akv_attention_executor_t executor,
                                      void *executor_context) {
  return attention_execute(plan, AKV_ATTENTION_KERNEL_VERSION_V2, executor,
                           executor_context);
}
