#include "qbs/qbs.h"

#include <limits.h>
#include <stdbool.h>
#include <string.h>

#define QBS_CAP_BLOCKING_COMPLETION (UINT64_C(1) << 43)
#define QBS_CAP_FAULT_ATOMIC_DESTINATION (UINT64_C(1) << 44)
#define QBS_CAP_REQUIRES_VSTART_ZERO (UINT64_C(1) << 45)
#define QBS_CAP_IDEMPOTENT_MEMORY_ONLY (UINT64_C(1) << 46)
#define QBS_CAP_REQUIRES_ACCEL_CONSISTENCY (UINT64_C(1) << 47)

static bool size_mul(size_t lhs, size_t rhs, size_t *result) {
  if (lhs != 0 && rhs > SIZE_MAX / lhs) return false;
  *result = lhs * rhs;
  return true;
}

static bool size_add(size_t lhs, size_t rhs, size_t *result) {
  if (rhs > SIZE_MAX - lhs) return false;
  *result = lhs + rhs;
  return true;
}

static size_t align_up(size_t value, size_t alignment) {
  if (alignment == 0 || value > SIZE_MAX - (alignment - 1u)) return 0;
  return (value + alignment - 1u) & ~(alignment - 1u);
}

const char *qbs_status_string(qbs_status_t status) {
  switch (status) {
    case QBS_STATUS_OK: return "ok";
    case QBS_STATUS_BAD_ARGUMENT: return "bad_argument";
    case QBS_STATUS_SIZE_OVERFLOW: return "size_overflow";
    case QBS_STATUS_BUFFER_TOO_SMALL: return "buffer_too_small";
    case QBS_STATUS_BUFFER_ALIGNMENT: return "buffer_alignment";
    case QBS_STATUS_RUNTIME_UNAVAILABLE: return "runtime_unavailable";
    case QBS_STATUS_ABI_MISMATCH: return "abi_mismatch";
    case QBS_STATUS_NUMERICAL_CONTRACT: return "numerical_contract";
    case QBS_STATUS_CAPABILITY: return "capability";
    case QBS_STATUS_PROFILE: return "profile";
    case QBS_STATUS_PROFILE_PAIR: return "profile_pair";
    case QBS_STATUS_LAYOUT: return "layout";
    case QBS_STATUS_SHAPE: return "shape";
    case QBS_STATUS_EXECUTION: return "execution";
  }
  return "unknown";
}

qbs_status_t qbs_weight_profile_info(unsigned profile,
                                     qbs_weight_profile_info_t *info) {
  if (info == NULL) return QBS_STATUS_BAD_ARGUMENT;
  const unsigned block_bytes = qbs_weight_block_bytes(profile);
  const unsigned block_elements = qbs_weight_block_elements(profile);
  if (block_bytes == 0 || block_elements == 0) return QBS_STATUS_PROFILE;
  uint16_t compatible_activation_profiles = 0;
  for (unsigned activation = 1; activation < 16; ++activation) {
    if (qbs_profiles_compatible(profile, activation)) {
      compatible_activation_profiles |=
          (uint16_t)(UINT16_C(1) << activation);
    }
  }
  *info = (qbs_weight_profile_info_t) {
      .id = (uint8_t)profile,
      .block_bytes = (uint16_t)block_bytes,
      .block_elements = (uint16_t)block_elements,
      .subgroup_count = (uint8_t)qbs_weight_subgroup_count(profile),
      .subgroup_elements = (uint8_t)qbs_weight_subgroup_elements(profile),
      .scale_format = (uint8_t)qbs_weight_scale_format(profile),
      .correction_mode = (uint8_t)qbs_weight_correction_mode(profile),
      .compatible_activation_profiles = compatible_activation_profiles,
  };
  return QBS_STATUS_OK;
}

qbs_status_t qbs_activation_profile_info(
    unsigned profile, qbs_activation_profile_info_t *info) {
  if (info == NULL) return QBS_STATUS_BAD_ARGUMENT;
  const unsigned block_bytes = qbs_activation_block_bytes(profile);
  const unsigned block_elements = qbs_activation_block_elements(profile);
  if (block_bytes == 0 || block_elements == 0) return QBS_STATUS_PROFILE;
  *info = (qbs_activation_profile_info_t) {
      .id = (uint8_t)profile,
      .block_bytes = (uint16_t)block_bytes,
      .block_elements = (uint16_t)block_elements,
      .scale_format = (uint8_t)qbs_activation_scale_format(profile),
      .scale_bytes = (uint8_t)qbs_activation_scale_bytes(profile),
      .quant_bytes = (uint16_t)qbs_activation_quant_bytes(profile),
      .aux_count = (uint8_t)qbs_activation_aux_count(profile),
      .aux_element_bytes =
          (uint8_t)qbs_activation_aux_element_bytes(profile),
  };
  return QBS_STATUS_OK;
}

qbs_status_t qbs_capabilities_decode(uint64_t info0, uint64_t info1,
                                     qbs_capabilities_t *capabilities) {
  if (capabilities == NULL) return QBS_STATUS_BAD_ARGUMENT;
  memset(capabilities, 0, sizeof(*capabilities));
  if (info0 == 0 || info1 == 0) return QBS_STATUS_RUNTIME_UNAVAILABLE;

  capabilities->architecture_version = (uint8_t)(info0 & 0xffu);
  capabilities->descriptor_version = (uint8_t)((info0 >> 8) & 0xffu);
  capabilities->descriptor_bytes = (uint8_t)((info0 >> 16) & 0xffu);
  capabilities->max_m = (uint8_t)(((info0 >> 24) & 0x03u) + 1u);
  capabilities->max_n = (uint8_t)(((info0 >> 26) & 0x1fu) + 1u);
  capabilities->max_k_blocks =
      (uint16_t)(((info0 >> 31) & 0xffu) + 1u);
  capabilities->numerical_contract_version =
      (uint8_t)((info0 >> 39) & 0x0fu);
  capabilities->blocking_completion =
      (info0 & QBS_CAP_BLOCKING_COMPLETION) != 0;
  capabilities->fault_atomic_destination =
      (info0 & QBS_CAP_FAULT_ATOMIC_DESTINATION) != 0;
  capabilities->requires_vstart_zero =
      (info0 & QBS_CAP_REQUIRES_VSTART_ZERO) != 0;
  capabilities->idempotent_memory_only =
      (info0 & QBS_CAP_IDEMPOTENT_MEMORY_ONLY) != 0;
  capabilities->requires_accelerator_consistency =
      (info0 & QBS_CAP_REQUIRES_ACCEL_CONSISTENCY) != 0;
  capabilities->weight_layouts = (uint16_t)(info1 & 0xffffu);
  capabilities->activation_layouts = (uint16_t)((info1 >> 16) & 0xffffu);
  capabilities->descriptor_alignment_log2 =
      (uint8_t)((info1 >> 32) & 0xffu);
  capabilities->weight_alignment_log2 =
      (uint8_t)((info1 >> 40) & 0xffu);
  capabilities->activation_alignment_log2 =
      (uint8_t)((info1 >> 48) & 0xffu);
  capabilities->result_element_bits = (uint8_t)((info1 >> 56) & 0xffu);

  if (capabilities->architecture_version != QBS_ARCH_VERSION ||
      capabilities->descriptor_version != QBS_DESCRIPTOR_VERSION ||
      capabilities->descriptor_bytes != QBS_DESCRIPTOR_BYTES) {
    return QBS_STATUS_ABI_MISMATCH;
  }
  if (capabilities->numerical_contract_version !=
      QBS_NUMERICAL_CONTRACT_VERSION) {
    return QBS_STATUS_NUMERICAL_CONTRACT;
  }
  if (!capabilities->blocking_completion ||
      !capabilities->fault_atomic_destination ||
      !capabilities->requires_vstart_zero ||
      !capabilities->idempotent_memory_only ||
      !capabilities->requires_accelerator_consistency ||
      capabilities->descriptor_alignment_log2 !=
          QBS_DESCRIPTOR_ALIGNMENT_LOG2 ||
      capabilities->weight_alignment_log2 !=
          QBS_WEIGHT_BASE_ALIGNMENT_LOG2 ||
      capabilities->activation_alignment_log2 !=
          QBS_ACTIVATION_BASE_ALIGNMENT_LOG2 ||
      capabilities->result_element_bits != 32u) {
    return QBS_STATUS_CAPABILITY;
  }
  capabilities->valid = 1;
  return QBS_STATUS_OK;
}

static uint64_t reference_info(void *context, unsigned index) {
  return qbs_capability_word(index, *(const unsigned *)context);
}

qbs_status_t qbs_device_query(qbs_info_reader_t reader, void *context,
                              qbs_device_t *device) {
  if (reader == NULL || device == NULL) return QBS_STATUS_BAD_ARGUMENT;
  memset(device, 0, sizeof(*device));
  qbs_status_t status = qbs_capabilities_decode(
      reader(context, 0), reader(context, 1), &device->capabilities);
  if (status != QBS_STATUS_OK) return status;

  const unsigned vlen_bits = (unsigned)device->capabilities.max_n * 32u;
  for (unsigned profile = 1; profile < 16; ++profile) {
    qbs_weight_profile_info_t info;
    if (qbs_weight_profile_info(profile, &info) != QBS_STATUS_OK) continue;
    const uint64_t implementation = reader(context, 0x20u + profile);
    const uint64_t contract = qbs_capability_word(0x20u + profile, vlen_bits);
    if (implementation == 0 || implementation != contract) continue;
    const uint16_t compatible =
        (uint16_t)reader(context, 0x10u + profile) &
        (uint16_t)qbs_capability_word(0x10u + profile, vlen_bits);
    if (compatible == 0) continue;
    device->weight_profiles |= (uint16_t)(UINT16_C(1) << profile);
    device->compatible_activation_profiles[profile] = compatible;
  }
  for (unsigned profile = 1; profile < 16; ++profile) {
    qbs_activation_profile_info_t info;
    if (qbs_activation_profile_info(profile, &info) != QBS_STATUS_OK) continue;
    const uint64_t implementation = reader(context, 0x30u + profile);
    const uint64_t contract = qbs_capability_word(0x30u + profile, vlen_bits);
    if (implementation != 0 && implementation == contract) {
      device->activation_profiles |=
          (uint16_t)(UINT16_C(1) << profile);
    }
  }
  for (unsigned profile = 1; profile < 16; ++profile) {
    device->compatible_activation_profiles[profile] &=
        device->activation_profiles;
    if (device->compatible_activation_profiles[profile] == 0) {
      device->weight_profiles &= (uint16_t)~(UINT16_C(1) << profile);
    }
  }
  return device->weight_profiles != 0 && device->activation_profiles != 0
             ? QBS_STATUS_OK
             : QBS_STATUS_PROFILE;
}

qbs_status_t qbs_device_init_reference(unsigned vlen_bits,
                                       qbs_device_t *device) {
  if (vlen_bits < 32 || vlen_bits % 32u != 0)
    return QBS_STATUS_BAD_ARGUMENT;
  return qbs_device_query(reference_info, &vlen_bits, device);
}

int qbs_device_supports_profile(const qbs_device_t *device,
                                unsigned weight_profile,
                                unsigned activation_profile) {
  if (device == NULL || !device->capabilities.valid ||
      weight_profile >= 16 || activation_profile >= 16) return 0;
  return (device->weight_profiles & (UINT16_C(1) << weight_profile)) != 0 &&
      (device->activation_profiles &
       (UINT16_C(1) << activation_profile)) != 0 &&
      (device->compatible_activation_profiles[weight_profile] &
       (UINT16_C(1) << activation_profile)) != 0;
}

qbs_status_t qbs_device_bind_encodings(
    const qbs_device_t *device, uint64_t weight_encoding_id,
    uint64_t activation_encoding_id, qbs_profile_binding_t *binding) {
  if (device == NULL || binding == NULL || weight_encoding_id == 0 ||
      activation_encoding_id == 0)
    return QBS_STATUS_BAD_ARGUMENT;
  memset(binding, 0, sizeof(*binding));

  const qbs_weight_profile_t weight_profile =
      qbs_weight_profile_from_encoding(weight_encoding_id);
  const qbs_activation_profile_t activation_profile =
      qbs_activation_profile_from_encoding(activation_encoding_id);
  if (weight_profile == QBS_WEIGHT_PROFILE_INVALID ||
      activation_profile == QBS_ACTIVATION_PROFILE_INVALID)
    return QBS_STATUS_PROFILE;
  if (!qbs_profiles_compatible(weight_profile, activation_profile))
    return QBS_STATUS_PROFILE_PAIR;
  if (!device->capabilities.valid ||
      !qbs_device_supports_profile(device, weight_profile, activation_profile))
    return QBS_STATUS_CAPABILITY;

  *binding = (qbs_profile_binding_t) {
      .weight_encoding_id = weight_encoding_id,
      .activation_encoding_id = activation_encoding_id,
      .weight_profile = (uint8_t)weight_profile,
      .activation_profile = (uint8_t)activation_profile,
  };
  return QBS_STATUS_OK;
}

size_t qbs_weight_storage_bytes(unsigned weight_profile,
                                unsigned weight_layout, size_t n,
                                size_t k_blocks) {
  const size_t block_bytes = qbs_weight_block_bytes(weight_profile);
  if (block_bytes == 0 || n == 0 || k_blocks == 0) return 0;
  size_t rows = n;
  if (weight_layout == QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR) {
    if (n > SIZE_MAX - 3u) return 0;
    rows = (n + 3u) & ~(size_t)3u;
  } else if (weight_layout != QBS_WEIGHT_LAYOUT_ROW_MAJOR) {
    return 0;
  }
  size_t blocks;
  size_t bytes;
  return size_mul(rows, k_blocks, &blocks) &&
                 size_mul(blocks, block_bytes, &bytes)
             ? bytes
             : 0;
}

size_t qbs_activation_storage_bytes(unsigned activation_profile,
                                    unsigned activation_storage, size_t m,
                                    size_t k_blocks) {
  const size_t block_bytes = qbs_activation_block_bytes(activation_profile);
  if (block_bytes == 0 || m == 0 || k_blocks == 0 ||
      (activation_storage != QBS_ACTIVATION_STORAGE_ROW_MAJOR &&
       activation_storage != QBS_ACTIVATION_STORAGE_M4_GROUPED)) return 0;
  size_t blocks;
  size_t bytes;
  return size_mul(m, k_blocks, &blocks) &&
                 size_mul(blocks, block_bytes, &bytes)
             ? bytes
             : 0;
}

qbs_status_t qbs_repack_weight_r4(unsigned weight_profile,
                                  const void *row_major,
                                  size_t row_major_bytes, size_t n,
                                  size_t k_blocks, void *r4,
                                  size_t r4_bytes) {
  if (row_major == NULL || r4 == NULL || n == 0 || k_blocks == 0)
    return QBS_STATUS_BAD_ARGUMENT;
  const size_t block_bytes = qbs_weight_block_bytes(weight_profile);
  const size_t source_bytes = qbs_weight_storage_bytes(
      weight_profile, QBS_WEIGHT_LAYOUT_ROW_MAJOR, n, k_blocks);
  const size_t destination_bytes = qbs_weight_storage_bytes(
      weight_profile, QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR, n, k_blocks);
  if (block_bytes == 0) return QBS_STATUS_PROFILE;
  if (source_bytes == 0 || destination_bytes == 0)
    return QBS_STATUS_SIZE_OVERFLOW;
  if (row_major_bytes < source_bytes || r4_bytes < destination_bytes)
    return QBS_STATUS_BUFFER_TOO_SMALL;

  memset(r4, 0, destination_bytes);
  for (size_t row = 0; row < n; ++row) {
    for (size_t block = 0; block < k_blocks; ++block) {
      const size_t source_index = row * k_blocks + block;
      const size_t destination_index =
          ((row / 4u) * k_blocks + block) * 4u + row % 4u;
      memcpy((uint8_t *)r4 + destination_index * block_bytes,
             (const uint8_t *)row_major + source_index * block_bytes,
             block_bytes);
    }
  }
  return QBS_STATUS_OK;
}

qbs_status_t qbs_pack_activation_m4(unsigned activation_profile,
                                    const void *row_major,
                                    size_t row_major_bytes, size_t k_blocks,
                                    void *interleaved,
                                    size_t interleaved_bytes) {
  if (row_major == NULL || interleaved == NULL || k_blocks == 0)
    return QBS_STATUS_BAD_ARGUMENT;
  qbs_activation_profile_info_t profile;
  qbs_status_t status = qbs_activation_profile_info(activation_profile,
                                                    &profile);
  if (status != QBS_STATUS_OK) return status;
  size_t required;
  if (!size_mul(4u * k_blocks, profile.block_bytes, &required))
    return QBS_STATUS_SIZE_OVERFLOW;
  if (row_major_bytes < required || interleaved_bytes < required)
    return QBS_STATUS_BUFFER_TOO_SMALL;

  for (size_t block = 0; block < k_blocks; ++block) {
    uint8_t *destination =
        (uint8_t *)interleaved + block * 4u * profile.block_bytes;
    for (size_t context = 0; context < 4; ++context) {
      const uint8_t *source = (const uint8_t *)row_major +
          (context * k_blocks + block) * profile.block_bytes;
      memcpy(destination + context * profile.scale_bytes, source,
             profile.scale_bytes);
      for (size_t byte = 0; byte < profile.quant_bytes; ++byte) {
        destination[4u * profile.scale_bytes + byte * 4u + context] =
            source[profile.scale_bytes + byte];
      }
      for (size_t item = 0; item < profile.aux_count; ++item) {
        const size_t source_offset = profile.scale_bytes +
            profile.quant_bytes + item * profile.aux_element_bytes;
        const size_t destination_offset = 4u * profile.scale_bytes +
            4u * profile.quant_bytes +
            (item * 4u + context) * profile.aux_element_bytes;
        memcpy(destination + destination_offset, source + source_offset,
               profile.aux_element_bytes);
      }
    }
  }
  return QBS_STATUS_OK;
}

static unsigned max_command_m(const qbs_plan_t *plan) {
  if (plan->problem.activation_storage == QBS_ACTIVATION_STORAGE_M4_GROUPED &&
      plan->problem.m >= 4u) {
    return 4u;
  }
  return plan->problem.m < plan->command_m ? (unsigned)plan->problem.m
                                            : plan->command_m;
}

static unsigned max_non_m4_command_m(const qbs_plan_t *plan) {
  uint32_t rows = plan->problem.m;
  if (plan->problem.activation_storage == QBS_ACTIVATION_STORAGE_M4_GROUPED) {
    rows %= 4u;
  }
  return rows < plan->command_m ? (unsigned)rows : plan->command_m;
}

static bool block_offset_aligned(size_t factor_a, size_t factor_b,
                                 size_t block_bytes, size_t alignment) {
  size_t remainder = (factor_a % alignment) * (factor_b % alignment);
  remainder = (remainder % alignment) * (block_bytes % alignment);
  return remainder % alignment == 0;
}

static bool plan_needs_activation_gather(const qbs_plan_t *plan,
                                         size_t activation_block_bytes) {
  const unsigned gather_rows = max_non_m4_command_m(plan);
  if (gather_rows == 0) return false;
  if (plan->split_k && gather_rows > 1u) return true;

  const size_t alignment = (size_t)1u << QBS_ACTIVATION_BASE_ALIGNMENT_LOG2;
  if (plan->split_k &&
      !block_offset_aligned(plan->command_k_blocks, 1u, activation_block_bytes,
                            alignment)) {
    return true;
  }
  if (plan->problem.activation_storage == QBS_ACTIVATION_STORAGE_ROW_MAJOR) {
    return plan->problem.m > plan->command_m &&
           !block_offset_aligned(plan->command_m, plan->k_blocks,
                                 activation_block_bytes, alignment);
  }

  if (plan->problem.m < 4u) {
    return plan->problem.m > plan->command_m &&
           !block_offset_aligned(plan->command_m, plan->k_blocks,
                                 activation_block_bytes, alignment);
  }

  const uint32_t tail_start = plan->problem.m - plan->problem.m % 4u;
  return tail_start != 0 &&
         !block_offset_aligned(tail_start, plan->k_blocks,
                               activation_block_bytes, alignment);
}

qbs_status_t qbs_plan_create(const qbs_device_t *device,
                             const qbs_problem_t *problem,
                             qbs_plan_t *plan) {
  if (device == NULL || problem == NULL || plan == NULL)
    return QBS_STATUS_BAD_ARGUMENT;
  memset(plan, 0, sizeof(*plan));
  if (!device->capabilities.valid) return QBS_STATUS_CAPABILITY;
  if (!qbs_device_supports_profile(device, problem->weight_profile,
                                   problem->activation_profile))
    return QBS_STATUS_PROFILE_PAIR;

  qbs_weight_profile_info_t weight;
  qbs_activation_profile_info_t activation;
  if (qbs_weight_profile_info(problem->weight_profile, &weight) !=
          QBS_STATUS_OK ||
      qbs_activation_profile_info(problem->activation_profile, &activation) !=
          QBS_STATUS_OK) return QBS_STATUS_PROFILE;
  if (weight.block_elements != activation.block_elements)
    return QBS_STATUS_PROFILE_PAIR;
  if (problem->m == 0 || problem->n == 0 || problem->k_elements == 0 ||
      problem->k_elements % weight.block_elements != 0)
    return QBS_STATUS_SHAPE;
  const uint32_t k_blocks = problem->k_elements / weight.block_elements;
  if (k_blocks == 0 || k_blocks > UINT16_MAX ||
      device->capabilities.max_m == 0 ||
      device->capabilities.max_n == 0 ||
      device->capabilities.max_k_blocks == 0)
    return QBS_STATUS_SHAPE;
  if (problem->weight_layout != QBS_WEIGHT_LAYOUT_ROW_MAJOR &&
      problem->weight_layout != QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR)
    return QBS_STATUS_LAYOUT;
  if ((device->capabilities.weight_layouts &
       (UINT16_C(1) << problem->weight_layout)) == 0)
    return QBS_STATUS_LAYOUT;
  if (problem->activation_storage != QBS_ACTIVATION_STORAGE_ROW_MAJOR &&
      problem->activation_storage != QBS_ACTIVATION_STORAGE_M4_GROUPED)
    return QBS_STATUS_LAYOUT;
  if ((device->capabilities.activation_layouts &
       (UINT16_C(1) << QBS_ACTIVATION_LAYOUT_ROW_MAJOR)) == 0)
    return QBS_STATUS_LAYOUT;
  if (problem->activation_storage == QBS_ACTIVATION_STORAGE_M4_GROUPED &&
      problem->m >= 4 &&
      (device->capabilities.max_m < 4 ||
       (device->capabilities.activation_layouts &
        (UINT16_C(1) << QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED)) == 0))
    return QBS_STATUS_LAYOUT;

  size_t output_elements;
  if (qbs_weight_storage_bytes(problem->weight_profile,
                               problem->weight_layout, problem->n,
                               k_blocks) == 0 ||
      qbs_activation_storage_bytes(problem->activation_profile,
                                   problem->activation_storage, problem->m,
                                   k_blocks) == 0 ||
      !size_mul(problem->m, problem->n, &output_elements))
    return QBS_STATUS_SIZE_OVERFLOW;

  *plan = (qbs_plan_t) {
      .problem = *problem,
      .k_blocks = (uint16_t)k_blocks,
      .command_k_blocks = device->capabilities.max_k_blocks,
      .command_m = device->capabilities.max_m,
  };
  if (plan->command_k_blocks > QBS_MAX_K_BLOCKS)
    plan->command_k_blocks = QBS_MAX_K_BLOCKS;
  if (plan->command_m > QBS_MAX_M) plan->command_m = QBS_MAX_M;
  plan->split_k = k_blocks > plan->command_k_blocks;

  if (problem->weight_layout == QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR) {
    if (device->capabilities.max_n < 4) return QBS_STATUS_CAPABILITY;
    plan->command_n = plan->split_k
        ? 4u : (uint8_t)(device->capabilities.max_n & ~3u);
  } else {
    plan->command_n = plan->split_k ? 1u : device->capabilities.max_n;
  }
  if (plan->command_n > QBS_MAX_N) plan->command_n = QBS_MAX_N;
  if (plan->command_n == 0) return QBS_STATUS_CAPABILITY;

  plan->needs_activation_gather =
      plan_needs_activation_gather(plan, activation.block_bytes);
  if (plan->split_k) {
    size_t partial_elements;
    size_t partial_bytes;
    if (!size_mul(max_command_m(plan), plan->command_n, &partial_elements) ||
        !size_mul(partial_elements, sizeof(float), &partial_bytes))
      return QBS_STATUS_SIZE_OVERFLOW;
    plan->workspace_bytes = align_up(partial_bytes, 4u);
    if (plan->workspace_bytes == 0) return QBS_STATUS_SIZE_OVERFLOW;
  }
  if (plan->needs_activation_gather) {
    const unsigned gather_rows = max_non_m4_command_m(plan);
    const size_t gather_k_blocks = plan->split_k
        ? plan->command_k_blocks : plan->k_blocks;
    size_t gather_blocks;
    size_t gather_bytes;
    if (!size_mul(gather_rows, gather_k_blocks, &gather_blocks) ||
        !size_mul(gather_blocks, activation.block_bytes, &gather_bytes) ||
        !size_add(plan->workspace_bytes, gather_bytes, &plan->workspace_bytes))
      return QBS_STATUS_SIZE_OVERFLOW;
  }
  return QBS_STATUS_OK;
}

void qbs_plan_cursor_reset(qbs_plan_cursor_t *cursor) {
  if (cursor != NULL) memset(cursor, 0, sizeof(*cursor));
}

static unsigned command_m(const qbs_plan_t *plan, uint32_t input_start) {
  const uint32_t remaining = plan->problem.m - input_start;
  if (plan->problem.activation_storage == QBS_ACTIVATION_STORAGE_M4_GROUPED &&
      remaining >= 4u) return 4u;
  return remaining < plan->command_m ? remaining : plan->command_m;
}

qbs_status_t qbs_plan_next(const qbs_plan_t *plan,
                           qbs_plan_cursor_t *cursor,
                           qbs_command_t *command, int *has_command) {
  if (plan == NULL || cursor == NULL || command == NULL ||
      has_command == NULL) return QBS_STATUS_BAD_ARGUMENT;
  *has_command = 0;
  if (cursor->done || cursor->input_start >= plan->problem.m) return QBS_STATUS_OK;

  const unsigned m = command_m(plan, cursor->input_start);
  const unsigned n_remaining = plan->problem.n - cursor->output_start;
  const unsigned n = n_remaining < plan->command_n
      ? n_remaining : plan->command_n;
  const unsigned k_remaining = plan->k_blocks - cursor->k_block_start;
  const unsigned k_blocks = k_remaining < plan->command_k_blocks
      ? k_remaining : plan->command_k_blocks;
  const bool m4 = plan->problem.activation_storage ==
          QBS_ACTIVATION_STORAGE_M4_GROUPED && m == 4u;
  const size_t weight_block_bytes =
      qbs_weight_block_bytes(plan->problem.weight_profile);
  const size_t activation_block_bytes =
      qbs_activation_block_bytes(plan->problem.activation_profile);
  size_t weight_block_index;
  if (plan->problem.weight_layout == QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR) {
    weight_block_index = (size_t)cursor->output_start * plan->k_blocks +
        (size_t)cursor->k_block_start * 4u;
  } else {
    weight_block_index = (size_t)cursor->output_start * plan->k_blocks +
        cursor->k_block_start;
  }
  size_t activation_block_index = (size_t)cursor->input_start *
      plan->k_blocks;
  if (plan->split_k)
    activation_block_index += m4
        ? (size_t)cursor->k_block_start * 4u
        : cursor->k_block_start;
  const size_t activation_offset_bytes =
      activation_block_index * activation_block_bytes;
  const size_t activation_alignment =
      (size_t)1u << QBS_ACTIVATION_BASE_ALIGNMENT_LOG2;
  const bool gather = !m4 &&
      ((plan->split_k && m > 1u) ||
       (activation_offset_bytes & (activation_alignment - 1u)) != 0);

  *command = (qbs_command_t) {
      .input_start = cursor->input_start,
      .output_start = cursor->output_start,
      .k_block_start = cursor->k_block_start,
      .k_blocks = (uint16_t)k_blocks,
      .m = (uint8_t)m,
      .n = (uint8_t)n,
      .activation_layout = m4 ? QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED
                              : QBS_ACTIVATION_LAYOUT_ROW_MAJOR,
      .accumulate = (uint8_t)(plan->split_k && cursor->k_block_start != 0),
      .gather_activation = (uint8_t)gather,
      .weight_offset_bytes = weight_block_index * weight_block_bytes,
      .activation_offset_bytes = activation_offset_bytes,
      .output_offset_elements =
          (size_t)cursor->input_start * plan->problem.n +
          cursor->output_start,
  };
  *has_command = 1;

  cursor->output_start += n;
  if (cursor->output_start >= plan->problem.n) {
    cursor->output_start = 0;
    if (plan->split_k) {
      cursor->k_block_start += k_blocks;
      if (cursor->k_block_start >= plan->k_blocks) {
        cursor->k_block_start = 0;
        cursor->input_start += m;
      }
    } else {
      cursor->input_start += m;
    }
  }
  if (cursor->input_start >= plan->problem.m) cursor->done = 1;
  return QBS_STATUS_OK;
}

qbs_status_t qbs_execute(const qbs_plan_t *plan, const void *weights,
                         size_t weights_bytes, const void *activations,
                         size_t activations_bytes, float *output,
                         size_t output_capacity_elements,
                         size_t output_stride_elements, void *workspace,
                         size_t workspace_bytes,
                         qbs_command_executor_t executor,
                         void *executor_context) {
  if (plan == NULL || weights == NULL || activations == NULL ||
      output == NULL || executor == NULL ||
      output_stride_elements < plan->problem.n)
    return QBS_STATUS_BAD_ARGUMENT;

  const size_t required_weights = qbs_weight_storage_bytes(
      plan->problem.weight_profile, plan->problem.weight_layout,
      plan->problem.n, plan->k_blocks);
  const size_t required_activations = qbs_activation_storage_bytes(
      plan->problem.activation_profile, plan->problem.activation_storage,
      plan->problem.m, plan->k_blocks);
  size_t output_row_offset;
  size_t required_output_elements;
  if (required_weights == 0 || required_activations == 0 ||
      !size_mul(plan->problem.m - 1u, output_stride_elements,
                &output_row_offset) ||
      !size_add(output_row_offset, plan->problem.n,
                &required_output_elements))
    return QBS_STATUS_SIZE_OVERFLOW;
  if (weights_bytes < required_weights ||
      activations_bytes < required_activations ||
      output_capacity_elements < required_output_elements)
    return QBS_STATUS_BUFFER_TOO_SMALL;
  const uintptr_t weight_alignment =
      (uintptr_t)1u << QBS_WEIGHT_BASE_ALIGNMENT_LOG2;
  const uintptr_t activation_alignment =
      (uintptr_t)1u << QBS_ACTIVATION_BASE_ALIGNMENT_LOG2;
  if (((uintptr_t)weights & (weight_alignment - 1u)) != 0 ||
      ((uintptr_t)activations & (activation_alignment - 1u)) != 0 ||
      ((uintptr_t)output & (_Alignof(float) - 1u)) != 0)
    return QBS_STATUS_BUFFER_ALIGNMENT;
  if (plan->workspace_bytes != 0) {
    if (workspace == NULL || workspace_bytes < plan->workspace_bytes)
      return QBS_STATUS_BUFFER_TOO_SMALL;
    if (((uintptr_t)workspace & (_Alignof(float) - 1u)) != 0)
      return QBS_STATUS_BUFFER_ALIGNMENT;
  }

  float *partial = (float *)workspace;
  const size_t partial_bytes = plan->split_k
      ? align_up((size_t)max_command_m(plan) * plan->command_n * sizeof(float),
                 4u)
      : 0;
  uint8_t *activation_gather = plan->workspace_bytes != 0
      ? (uint8_t *)workspace + partial_bytes : NULL;
  const size_t activation_block_bytes =
      qbs_activation_block_bytes(plan->problem.activation_profile);

  qbs_plan_cursor_t cursor;
  qbs_plan_cursor_reset(&cursor);
  for (;;) {
    qbs_command_t command;
    int has_command;
    qbs_status_t status = qbs_plan_next(plan, &cursor, &command, &has_command);
    if (status != QBS_STATUS_OK || !has_command) return status;

    const void *command_activation =
        (const uint8_t *)activations + command.activation_offset_bytes;
    if (command.gather_activation) {
      const size_t segment_bytes =
          (size_t)command.k_blocks * activation_block_bytes;
      for (unsigned row = 0; row < command.m; ++row) {
        const uint8_t *source = (const uint8_t *)activations +
            ((size_t)(command.input_start + row) * plan->k_blocks +
             command.k_block_start) * activation_block_bytes;
        memcpy(activation_gather + (size_t)row * segment_bytes, source,
               segment_bytes);
      }
      command_activation = activation_gather;
    }

    const qbs_descriptor_fields_t fields = {
        .descriptor_version = QBS_DESCRIPTOR_VERSION,
        .weight_profile = plan->problem.weight_profile,
        .activation_profile = plan->problem.activation_profile,
        .weight_layout = plan->problem.weight_layout,
        .activation_layout = command.activation_layout,
        .n = command.n,
        .k_blocks = command.k_blocks,
    };
    const qbs_descriptor_v1_t descriptor = {
        .header = qbs_pack_descriptor_header(&fields),
        .weight_base = (uintptr_t)((const uint8_t *)weights +
                                  command.weight_offset_bytes),
    };
    float *destination = output +
        (size_t)command.input_start * output_stride_elements +
        command.output_start;
    float *command_output = plan->split_k ? partial : destination;
    const size_t command_stride = plan->split_k
        ? command.n : output_stride_elements;
    status = executor(executor_context, &descriptor, command.m,
                      command_activation, command_output, command_stride,
                      command.n, plan->split_k);
    if (status != QBS_STATUS_OK) return status;
    if (plan->split_k) {
      for (unsigned row = 0; row < command.m; ++row) {
        for (unsigned column = 0; column < command.n; ++column) {
          float *element = destination +
              (size_t)row * output_stride_elements + column;
          const float value = partial[(size_t)row * command.n + column];
          if (command.accumulate) *element += value;
          else *element = value;
        }
      }
    }
  }
}
