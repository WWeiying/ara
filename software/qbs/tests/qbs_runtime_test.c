#include "qbs/qbs.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(condition)                                                    \
  do {                                                                      \
    if (!(condition)) {                                                     \
      fprintf(stderr, "CHECK failed at %s:%d: %s\n", __FILE__, __LINE__, \
              #condition);                                                  \
      return 1;                                                             \
    }                                                                       \
  } while (0)

static const unsigned weight_profiles[] = {
    QBS_WEIGHT_PROFILE_Q2_K,   QBS_WEIGHT_PROFILE_Q3_K,
    QBS_WEIGHT_PROFILE_Q4_K,   QBS_WEIGHT_PROFILE_Q5_K,
    QBS_WEIGHT_PROFILE_Q6_K,   QBS_WEIGHT_PROFILE_Q4_0,
    QBS_WEIGHT_PROFILE_Q5_0,   QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
    QBS_WEIGHT_PROFILE_IQ4_NL,
};

static int test_size_mul(size_t lhs, size_t rhs, size_t *result) {
  if (lhs != 0 && rhs > SIZE_MAX / lhs) return 0;
  *result = lhs * rhs;
  return 1;
}

typedef struct {
  unsigned vlen_bits;
  unsigned overridden_index;
  uint64_t overridden_value;
} capability_reader_t;

static uint64_t capability_reader(void *opaque, unsigned index) {
  const capability_reader_t *reader = (const capability_reader_t *)opaque;
  return index == reader->overridden_index
             ? reader->overridden_value
             : qbs_capability_word(index, reader->vlen_bits);
}

static int test_device_and_profiles(void) {
  qbs_device_t device;
  CHECK(qbs_device_init_reference(1024, &device) == QBS_STATUS_OK);
  CHECK(device.capabilities.valid);
  CHECK(device.capabilities.max_m == 8);
  CHECK(device.capabilities.max_n == 32);
  CHECK(device.capabilities.max_results == 128);
  CHECK(device.capabilities.max_k_blocks == 256);
  CHECK(device.capabilities.blocking_completion);
  CHECK(device.capabilities.fault_atomic_destination);
  CHECK(device.capabilities.requires_vstart_zero);
  CHECK(device.capabilities.idempotent_memory_only);
  CHECK(device.capabilities.requires_accelerator_consistency);
  CHECK(device.capabilities.activation_context_count == 1);
  CHECK(device.capabilities.activation_context_max_m == 1);
  CHECK(device.capabilities.activation_context_max_k_blocks == 16);
  CHECK(device.capabilities.activation_context_generation_bits == 8);
  CHECK(device.capabilities.activation_context_access_modes == 0x0f);
  CHECK(device.capabilities.activation_context_profiles ==
        (UINT16_C(1) << QBS_ACTIVATION_PROFILE_Q8_K));
  CHECK(device.capabilities.activation_context_layouts ==
        (UINT16_C(1) << QBS_ACTIVATION_LAYOUT_ROW_MAJOR));
  CHECK((device.capabilities.activation_layouts &
         (UINT16_C(1) << QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED)) != 0);

  for (size_t index = 0;
       index < sizeof(weight_profiles) / sizeof(weight_profiles[0]); ++index) {
    qbs_weight_profile_info_t weight;
    CHECK(qbs_weight_profile_info(weight_profiles[index], &weight) ==
          QBS_STATUS_OK);
    const unsigned activation = qbs_default_activation_profile(weight.id);
    qbs_activation_profile_info_t activation_info;
    CHECK(qbs_activation_profile_info(activation, &activation_info) ==
          QBS_STATUS_OK);
    const uint64_t weight_encoding_id = qbs_weight_encoding_id(weight.id);
    const uint64_t activation_encoding_id =
        qbs_activation_encoding_id(activation_info.id);
    CHECK(weight_encoding_id != 0 && activation_encoding_id != 0);
    CHECK(qbs_weight_profile_from_encoding(weight_encoding_id) == weight.id);
    CHECK(qbs_activation_profile_from_encoding(activation_encoding_id) ==
          activation_info.id);
    CHECK(strcmp(qbs_weight_encoding_name(weight.id), "invalid") != 0);
    CHECK(strcmp(qbs_activation_encoding_name(activation_info.id),
                 "invalid") != 0);
    CHECK(weight.block_elements == activation_info.block_elements);
    CHECK(strcmp(qbs_weight_profile_name(weight.id), "invalid") != 0);
    CHECK(strcmp(qbs_activation_profile_name(activation), "invalid") != 0);
    CHECK((weight.compatible_activation_profiles &
           (UINT16_C(1) << activation)) != 0);
    CHECK(qbs_device_supports_profile(&device, weight.id, activation));
    qbs_profile_binding_t binding;
    CHECK(qbs_device_bind_encodings(&device, weight_encoding_id,
                                    activation_encoding_id,
                                    &binding) == QBS_STATUS_OK);
    CHECK(binding.weight_profile == weight.id);
    CHECK(binding.activation_profile == activation_info.id);
    CHECK(binding.weight_encoding_id == weight_encoding_id);
    CHECK(binding.activation_encoding_id == activation_encoding_id);
    for (size_t other = 0; other < index; ++other) {
      CHECK(weight_encoding_id !=
            qbs_weight_encoding_id(weight_profiles[other]));
    }
  }
  CHECK(QBS_WEIGHT_ENCODING_S4_B32_F16_SPLIT_NIBBLE_OFFSET8 ==
        QBS_WEIGHT_ENCODING_Q4_0);
  CHECK(QBS_WEIGHT_ENCODING_S5_B32_F16_NIBBLE_HIGHBIT_OFFSET16 ==
        QBS_WEIGHT_ENCODING_Q5_0);
  CHECK(QBS_WEIGHT_ENCODING_S8_B32_F16_TWOS_COMPLEMENT ==
        QBS_WEIGHT_ENCODING_Q8_0_WEIGHT);
  CHECK(QBS_ACTIVATION_ENCODING_S8_B32_F16_TWOS_COMPLEMENT ==
        QBS_ACTIVATION_ENCODING_Q8_0);
  CHECK(QBS_ACTIVATION_ENCODING_S8_B256_F32_BSUM16_I16 ==
        QBS_ACTIVATION_ENCODING_Q8_K);
  CHECK(strcmp(qbs_weight_profile_name(15), "invalid") == 0);
  CHECK(strcmp(qbs_activation_profile_name(15), "invalid") == 0);
  CHECK(qbs_weight_profile_info(15, &(qbs_weight_profile_info_t){0}) ==
        QBS_STATUS_PROFILE);
  CHECK(!qbs_device_supports_profile(
      &device, QBS_WEIGHT_PROFILE_Q4_K, QBS_ACTIVATION_PROFILE_Q8_0));

  qbs_profile_binding_t binding = {.weight_profile = 0xffu};
  CHECK(qbs_device_bind_encodings(NULL, QBS_WEIGHT_ENCODING_Q4_K,
                                  QBS_ACTIVATION_ENCODING_Q8_K,
                                  &binding) == QBS_STATUS_BAD_ARGUMENT);
  CHECK(qbs_device_bind_encodings(&device, 0,
                                  QBS_ACTIVATION_ENCODING_Q8_K,
                                  &binding) == QBS_STATUS_BAD_ARGUMENT);
  CHECK(qbs_device_bind_encodings(&device, QBS_WEIGHT_ENCODING_Q4_K,
                                  QBS_ACTIVATION_ENCODING_Q8_K,
                                  NULL) == QBS_STATUS_BAD_ARGUMENT);
  CHECK(qbs_device_bind_encodings(&device, UINT64_C(0xdeadbeef),
                                  QBS_ACTIVATION_ENCODING_Q8_K,
                                  &binding) == QBS_STATUS_PROFILE);
  CHECK(binding.weight_profile == 0);
  CHECK(qbs_device_bind_encodings(&device, QBS_WEIGHT_ENCODING_Q4_K,
                                  QBS_ACTIVATION_ENCODING_Q8_0,
                                  &binding) == QBS_STATUS_PROFILE_PAIR);
  qbs_device_t restricted = device;
  restricted.weight_profiles &=
      (uint16_t)~(UINT16_C(1) << QBS_WEIGHT_PROFILE_Q4_K);
  CHECK(qbs_device_bind_encodings(&restricted, QBS_WEIGHT_ENCODING_Q4_K,
                                  QBS_ACTIVATION_ENCODING_Q8_K,
                                  &binding) == QBS_STATUS_CAPABILITY);

  qbs_capabilities_t caps;
  uint64_t info0 = qbs_capability_word(0, 1024);
  const uint64_t info1 = qbs_capability_word(1, 1024);
  CHECK(qbs_capabilities_decode(info0, info1, &caps) == QBS_STATUS_OK);
  info0 &= ~(UINT64_C(1) << 44);
  CHECK(qbs_capabilities_decode(info0, info1, &caps) ==
        QBS_STATUS_CAPABILITY);

  capability_reader_t reader = {
      .vlen_bits = 1024,
      .overridden_index = 0x10u + QBS_WEIGHT_PROFILE_Q4_K,
      .overridden_value = UINT64_C(1) << QBS_ACTIVATION_PROFILE_Q8_0,
  };
  CHECK(qbs_device_query(capability_reader, &reader, &device) == QBS_STATUS_OK);
  CHECK(!qbs_device_supports_profile(&device, QBS_WEIGHT_PROFILE_Q4_K,
                                     QBS_ACTIVATION_PROFILE_Q8_K));
  CHECK(!qbs_device_supports_profile(&device, QBS_WEIGHT_PROFILE_Q4_K,
                                     QBS_ACTIVATION_PROFILE_Q8_0));
  reader.overridden_value = (UINT64_C(1) << QBS_ACTIVATION_PROFILE_Q8_K) |
                            (UINT64_C(1) << QBS_ACTIVATION_PROFILE_Q8_0);
  CHECK(qbs_device_query(capability_reader, &reader, &device) == QBS_STATUS_OK);
  CHECK(qbs_device_supports_profile(&device, QBS_WEIGHT_PROFILE_Q4_K,
                                    QBS_ACTIVATION_PROFILE_Q8_K));
  CHECK(!qbs_device_supports_profile(&device, QBS_WEIGHT_PROFILE_Q4_K,
                                     QBS_ACTIVATION_PROFILE_Q8_0));
  return 0;
}

static int test_weight_repack(void) {
  const size_t n = 5;
  const size_t k_blocks = 2;
  const size_t block_bytes = QBS_Q4_0_BLOCK_BYTES;
  const size_t source_bytes = qbs_weight_storage_bytes(
      QBS_WEIGHT_PROFILE_Q4_0, QBS_WEIGHT_LAYOUT_ROW_MAJOR, n, k_blocks);
  const size_t destination_bytes = qbs_weight_storage_bytes(
      QBS_WEIGHT_PROFILE_Q4_0, QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR, n, k_blocks);
  CHECK(source_bytes == n * k_blocks * block_bytes);
  CHECK(destination_bytes == 8u * k_blocks * block_bytes);

  uint8_t *source = (uint8_t *)malloc(source_bytes + 7u);
  uint8_t *destination = (uint8_t *)malloc(destination_bytes);
  CHECK(source != NULL && destination != NULL);
  for (size_t block = 0; block < n * k_blocks; ++block)
    memset(source + block * block_bytes, (int)(block + 1u), block_bytes);
  CHECK(qbs_repack_weight_r4(QBS_WEIGHT_PROFILE_Q4_0, source, source_bytes + 7u,
                             n, k_blocks, destination,
                             destination_bytes) == QBS_STATUS_OK);
  for (size_t row = 0; row < n; ++row) {
    for (size_t block = 0; block < k_blocks; ++block) {
      const size_t destination_index =
          ((row / 4u) * k_blocks + block) * 4u + row % 4u;
      CHECK(destination[destination_index * block_bytes] ==
            source[(row * k_blocks + block) * block_bytes]);
    }
  }
  for (size_t row = n; row < 8u; ++row) {
    for (size_t block = 0; block < k_blocks; ++block) {
      const size_t destination_index =
          ((row / 4u) * k_blocks + block) * 4u + row % 4u;
      CHECK(destination[destination_index * block_bytes] == 0);
    }
  }
  free(destination);
  free(source);
  return 0;
}

static int test_activation_pack_profile(unsigned profile) {
  qbs_activation_profile_info_t info;
  CHECK(qbs_activation_profile_info(profile, &info) == QBS_STATUS_OK);
  const size_t k_blocks = 2;
  const size_t bytes = 4u * k_blocks * info.block_bytes;
  uint8_t *source = (uint8_t *)malloc(bytes);
  uint8_t *destination = (uint8_t *)malloc(bytes);
  CHECK(source != NULL && destination != NULL);
  for (size_t context = 0; context < 4u; ++context) {
    for (size_t block = 0; block < k_blocks; ++block) {
      uint8_t *item = source +
          (context * k_blocks + block) * info.block_bytes;
      for (size_t byte = 0; byte < info.block_bytes; ++byte)
        item[byte] = (uint8_t)(context * 53u + block * 17u + byte);
    }
  }
  memset(destination, 0, bytes);
  CHECK(qbs_pack_activation_m4(profile, source, bytes, k_blocks,
                               destination, bytes) == QBS_STATUS_OK);
  for (size_t block = 0; block < k_blocks; ++block) {
    const uint8_t *packed =
        destination + block * 4u * info.block_bytes;
    for (size_t context = 0; context < 4u; ++context) {
      const uint8_t *original = source +
          (context * k_blocks + block) * info.block_bytes;
      CHECK(memcmp(packed + context * info.scale_bytes, original,
                   info.scale_bytes) == 0);
      for (size_t byte = 0; byte < info.quant_bytes; ++byte) {
        CHECK(packed[4u * info.scale_bytes + byte * 4u + context] ==
              original[info.scale_bytes + byte]);
      }
      for (size_t item = 0; item < info.aux_count; ++item) {
        const size_t source_offset = info.scale_bytes + info.quant_bytes +
            item * info.aux_element_bytes;
        const size_t destination_offset = 4u * info.scale_bytes +
            4u * info.quant_bytes +
            (item * 4u + context) * info.aux_element_bytes;
        CHECK(memcmp(packed + destination_offset, original + source_offset,
                     info.aux_element_bytes) == 0);
      }
    }
  }
  free(destination);
  free(source);
  return 0;
}

static int test_activation_pack_m8_profile(unsigned profile, size_t m) {
  qbs_activation_profile_info_t info;
  CHECK(qbs_activation_profile_info(profile, &info) == QBS_STATUS_OK);
  CHECK(m >= QBS_WIDE_M_MIN);
  const size_t k_blocks = 2;
  const size_t source_bytes = m * k_blocks * info.block_bytes;
  const size_t tail = m & 7u;
  const size_t storage_rows =
      m + (tail >= QBS_WIDE_M_MIN ? QBS_MAX_M - tail : 0u);
  const size_t destination_bytes =
      storage_rows * k_blocks * info.block_bytes;
  uint8_t *source = (uint8_t *)malloc(source_bytes);
  uint8_t *destination = (uint8_t *)malloc(destination_bytes);
  CHECK(source != NULL && destination != NULL);
  for (size_t context = 0; context < m; ++context) {
    for (size_t block = 0; block < k_blocks; ++block) {
      uint8_t *item = source +
          (context * k_blocks + block) * info.block_bytes;
      for (size_t byte = 0; byte < info.block_bytes; ++byte)
        item[byte] = (uint8_t)(context * 37u + block * 19u + byte);
    }
  }
  memset(destination, 0xa5, destination_bytes);
  CHECK(qbs_pack_activation_m8_grouped(
            profile, source, source_bytes, m, k_blocks, destination,
            destination_bytes) ==
        QBS_STATUS_OK);

  size_t packed_offset = 0;
  for (size_t first = 0; first < m;) {
    const size_t remaining = m - first;
    const size_t rows = remaining > 4u
        ? (remaining < QBS_MAX_M ? remaining : QBS_MAX_M)
        : remaining;
    const size_t group_storage_rows = rows > 4u ? QBS_MAX_M : rows;
    const uint8_t *packed = destination + packed_offset;
    if (rows <= 4u) {
      CHECK(memcmp(packed, source + first * k_blocks * info.block_bytes,
                   rows * k_blocks * info.block_bytes) == 0);
      first += rows;
      packed_offset += rows * k_blocks * info.block_bytes;
      continue;
    }
    for (size_t block = 0; block < k_blocks; ++block) {
      const uint8_t *packed_block =
          packed + block * group_storage_rows * info.block_bytes;
      for (size_t context = 0; context < rows; ++context) {
        const uint8_t *original = source +
            ((first + context) * k_blocks + block) * info.block_bytes;
        CHECK(memcmp(packed_block + context * info.scale_bytes, original,
                     info.scale_bytes) == 0);
        for (size_t byte = 0; byte < info.quant_bytes; ++byte) {
          CHECK(packed_block[group_storage_rows * info.scale_bytes +
                             byte * group_storage_rows + context] ==
                original[info.scale_bytes + byte]);
        }
        for (size_t item = 0; item < info.aux_count; ++item) {
          const size_t source_offset = info.scale_bytes + info.quant_bytes +
              item * info.aux_element_bytes;
          const size_t destination_offset =
              group_storage_rows * info.scale_bytes +
              group_storage_rows * info.quant_bytes +
              (item * group_storage_rows + context) * info.aux_element_bytes;
          CHECK(memcmp(packed_block + destination_offset,
                       original + source_offset,
                       info.aux_element_bytes) == 0);
        }
      }
      for (size_t context = rows; context < group_storage_rows; ++context) {
        CHECK(memcmp(packed_block + context * info.scale_bytes,
                     (uint8_t[4]){0}, info.scale_bytes) == 0);
      }
    }
    packed_offset += group_storage_rows * k_blocks * info.block_bytes;
    first += rows;
  }
  CHECK(packed_offset == destination_bytes);
  free(destination);
  free(source);
  return 0;
}

typedef struct {
  const qbs_plan_t *plan;
  const uint8_t *weights;
  const uint8_t *activations;
  qbs_command_t commands[128];
  uint8_t observed_activation_access[128];
  size_t command_count;
  size_t next_command;
  uint8_t expect_activation_context;
  uint8_t activation_context_scope;
  qbs_activation_context_token_t expected_token;
} mock_executor_t;

static qbs_status_t mock_execute(
    void *opaque, const qbs_descriptor_t *descriptor, unsigned m,
    const void *activations, float *output, size_t output_stride,
    unsigned n, int segmented) {
  mock_executor_t *mock = (mock_executor_t *)opaque;
  if (mock->next_command >= mock->command_count)
    return QBS_STATUS_EXECUTION;
  const size_t command_index = mock->next_command++;
  const qbs_command_t *command = &mock->commands[command_index];
  const qbs_descriptor_fields_t fields =
      qbs_unpack_descriptor_header(descriptor->header);
  uint8_t expected_access = QBS_ACTIVATION_ACCESS_DIRECT;
  if (mock->expect_activation_context) {
    const int first = command->output_start == 0u;
    const int final = command->output_start + command->n >=
        mock->plan->problem.n;
    switch (mock->activation_context_scope) {
      case QBS_ACTIVATION_CONTEXT_SCOPE_OPERATION:
        expected_access = first ? QBS_ACTIVATION_ACCESS_FILL
            : (final ? QBS_ACTIVATION_ACCESS_RELEASE
                     : QBS_ACTIVATION_ACCESS_REUSE);
        break;
      case QBS_ACTIVATION_CONTEXT_SCOPE_FILL_KEEP:
        expected_access = first ? QBS_ACTIVATION_ACCESS_FILL
                                : QBS_ACTIVATION_ACCESS_REUSE;
        break;
      case QBS_ACTIVATION_CONTEXT_SCOPE_REUSE_KEEP:
        expected_access = QBS_ACTIVATION_ACCESS_REUSE;
        break;
      case QBS_ACTIVATION_CONTEXT_SCOPE_REUSE_RELEASE:
        expected_access = final ? QBS_ACTIVATION_ACCESS_RELEASE
                                : QBS_ACTIVATION_ACCESS_REUSE;
        break;
      default:
        return QBS_STATUS_EXECUTION;
    }
  }
  mock->observed_activation_access[command_index] = fields.activation_access;
  if (m != command->m || n != command->n ||
      fields.descriptor_version != QBS_DESCRIPTOR_VERSION ||
      fields.weight_profile != mock->plan->problem.weight_profile ||
      fields.activation_profile != mock->plan->problem.activation_profile ||
      fields.weight_layout != mock->plan->problem.weight_layout ||
      fields.activation_layout != command->activation_layout ||
      fields.k_blocks != command->k_blocks ||
      fields.activation_access != expected_access ||
      fields.context_id != (mock->expect_activation_context
          ? mock->expected_token.context_id : 0u) ||
      fields.context_generation != (mock->expect_activation_context
          ? mock->expected_token.generation : 0u) ||
      descriptor->weight_base !=
          (uintptr_t)(mock->weights + command->weight_offset_bytes) ||
      segmented != mock->plan->split_k)
    return QBS_STATUS_EXECUTION;
  if (!command->gather_activation &&
      activations != mock->activations + command->activation_offset_bytes)
    return QBS_STATUS_EXECUTION;
  if (command->gather_activation) {
    const size_t block_bytes = qbs_activation_block_bytes(
        mock->plan->problem.activation_profile);
    const size_t segment_bytes = (size_t)command->k_blocks * block_bytes;
    for (unsigned row = 0; row < m; ++row) {
      const uint8_t expected = mock->activations[
          ((size_t)(command->input_start + row) * mock->plan->k_blocks +
           command->k_block_start) * block_bytes];
      if (((const uint8_t *)activations)[row * segment_bytes] != expected)
        return QBS_STATUS_EXECUTION;
    }
  }
  for (unsigned row = 0; row < m; ++row)
    for (unsigned column = 0; column < n; ++column)
      output[(size_t)row * output_stride + column] =
          (float)command->k_blocks;
  return QBS_STATUS_OK;
}

static int collect_commands(const qbs_plan_t *plan, mock_executor_t *mock) {
  qbs_plan_cursor_t cursor;
  qbs_plan_cursor_reset(&cursor);
  for (;;) {
    int has_command = 0;
    CHECK(mock->command_count <
          sizeof(mock->commands) / sizeof(mock->commands[0]));
    CHECK(qbs_plan_next(plan, &cursor, &mock->commands[mock->command_count],
                        &has_command) == QBS_STATUS_OK);
    if (!has_command) break;
    ++mock->command_count;
  }
  return 0;
}

static int validate_plan_commands(const qbs_plan_t *plan) {
  const size_t weight_block_bytes =
      qbs_weight_block_bytes(plan->problem.weight_profile);
  const size_t activation_block_bytes =
      qbs_activation_block_bytes(plan->problem.activation_profile);
  const size_t weight_bytes = qbs_weight_storage_bytes(
      plan->problem.weight_profile, plan->problem.weight_layout,
      plan->problem.n, plan->k_blocks);
  const size_t activation_bytes = qbs_activation_storage_bytes(
      plan->problem.activation_profile, plan->problem.activation_storage,
      plan->problem.m, plan->k_blocks);
  const size_t activation_alignment = (size_t)1u
                                      << QBS_ACTIVATION_BASE_ALIGNMENT_LOG2;
  const size_t weight_alignment = (size_t)1u
                                  << QBS_WEIGHT_BASE_ALIGNMENT_LOG2;
  const unsigned largest_command_m =
      plan->problem.activation_storage == QBS_ACTIVATION_STORAGE_M8_GROUPED &&
              plan->problem.m >= QBS_WIDE_M_MIN
          ? (plan->problem.m < plan->command_m
                 ? (unsigned)plan->problem.m : plan->command_m)
          : (plan->problem.activation_storage ==
                         QBS_ACTIVATION_STORAGE_M4_GROUPED &&
                     plan->problem.m >= 4u
                 ? 4u
                 : (plan->problem.m < plan->command_m
                        ? (unsigned)plan->problem.m : plan->command_m));
  const size_t partial_bytes = plan->split_k
      ? (size_t)largest_command_m * plan->command_n * sizeof(float)
      : 0u;
  size_t max_gather_bytes = 0;
  qbs_plan_cursor_t cursor;
  qbs_plan_cursor_reset(&cursor);
  int saw_gather = 0;

  for (uint32_t input = 0; input < plan->problem.m;) {
    const uint32_t remaining = plan->problem.m - input;
    unsigned m;
    if (plan->problem.activation_storage ==
            QBS_ACTIVATION_STORAGE_M8_GROUPED &&
        remaining >= QBS_WIDE_M_MIN)
      m = remaining < plan->command_m ? (unsigned)remaining : plan->command_m;
    else if (plan->problem.activation_storage ==
                 QBS_ACTIVATION_STORAGE_M4_GROUPED &&
             remaining >= 4u)
      m = 4u;
    else {
      const unsigned narrow_limit = plan->command_m < 4u
          ? plan->command_m : 4u;
      m = remaining < narrow_limit ? (unsigned)remaining : narrow_limit;
    }
    const int m4 =
        plan->problem.activation_storage == QBS_ACTIVATION_STORAGE_M4_GROUPED &&
        m == 4u;
    const int m8 =
        plan->problem.activation_storage == QBS_ACTIVATION_STORAGE_M8_GROUPED &&
        m >= QBS_WIDE_M_MIN;
    const unsigned n_limit = m8 ? plan->wide_command_n : plan->command_n;
    for (uint16_t k_start = 0;;) {
      const unsigned k_blocks =
          plan->k_blocks - k_start < plan->command_k_blocks
              ? plan->k_blocks - k_start
              : plan->command_k_blocks;
      for (uint32_t output = 0; output < plan->problem.n;) {
        const unsigned n = plan->problem.n - output < n_limit
                               ? (unsigned)(plan->problem.n - output)
                               : n_limit;
        qbs_command_t command;
        int has_command = 0;
        CHECK(qbs_plan_next(plan, &cursor, &command, &has_command) ==
              QBS_STATUS_OK);
        CHECK(has_command);
        CHECK(command.input_start == input);
        CHECK(command.output_start == output);
        CHECK(command.k_block_start == k_start);
        CHECK(command.m == m && command.n == n);
        CHECK(command.k_blocks == k_blocks);
        CHECK(command.accumulate == (plan->split_k && k_start != 0));
        CHECK(command.activation_layout ==
              (m8 ? QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED
                  : (m4 ? QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED
                        : QBS_ACTIVATION_LAYOUT_ROW_MAJOR)));
        CHECK((size_t)command.m * command.n <= QBS_MAX_RESULTS);

        const size_t weight_block_index =
            plan->problem.weight_layout == QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR
                ? (size_t)output * plan->k_blocks + (size_t)k_start * 4u
                : (size_t)output * plan->k_blocks + k_start;
        size_t activation_block_index = (size_t)input * plan->k_blocks;
        if (plan->split_k) {
          activation_block_index += m4 ? (size_t)k_start * 4u : k_start;
        }
        const size_t activation_offset =
            activation_block_index * activation_block_bytes;
        const int gather = !m4 && !m8 &&
            ((plan->split_k && m > 1u) ||
             (activation_offset & (activation_alignment - 1u)) != 0);
        CHECK(command.gather_activation == gather);
        CHECK(command.weight_offset_bytes ==
              weight_block_index * weight_block_bytes);
        CHECK(command.activation_offset_bytes == activation_offset);
        CHECK(command.output_offset_elements ==
              (size_t)input * plan->problem.n + output);
        CHECK(command.weight_offset_bytes < weight_bytes);
        CHECK(command.activation_offset_bytes < activation_bytes);
        CHECK(command.weight_offset_bytes % weight_alignment == 0);
        size_t command_weight_rows = command.n;
        if (plan->problem.weight_layout ==
            QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR) {
          command_weight_rows = (command_weight_rows + 3u) & ~(size_t)3u;
        }
        size_t command_weight_bytes;
        CHECK(test_size_mul(command_weight_rows, command.k_blocks,
                            &command_weight_bytes));
        CHECK(test_size_mul(command_weight_bytes, weight_block_bytes,
                            &command_weight_bytes));
        CHECK(command_weight_bytes <=
              weight_bytes - command.weight_offset_bytes);
        if (!gather) {
          size_t directly_addressed_bytes;
          CHECK(command.activation_offset_bytes % activation_alignment == 0);
          CHECK(test_size_mul(command.m, command.k_blocks,
                              &directly_addressed_bytes));
          CHECK(test_size_mul(directly_addressed_bytes,
                              activation_block_bytes,
                              &directly_addressed_bytes));
          CHECK(directly_addressed_bytes <=
                activation_bytes - command.activation_offset_bytes);
        } else {
          size_t gather_bytes;
          CHECK(test_size_mul(command.m, command.k_blocks, &gather_bytes));
          CHECK(test_size_mul(gather_bytes, activation_block_bytes,
                              &gather_bytes));
          if (gather_bytes > max_gather_bytes) max_gather_bytes = gather_bytes;
          for (unsigned row = 0; row < command.m; ++row) {
            const size_t source_block =
                (size_t)(command.input_start + row) * plan->k_blocks +
                command.k_block_start;
            CHECK(source_block <= SIZE_MAX / activation_block_bytes);
            const size_t source_offset = source_block * activation_block_bytes;
            const size_t row_bytes =
                (size_t)command.k_blocks * activation_block_bytes;
            CHECK(source_offset <= activation_bytes);
            CHECK(row_bytes <= activation_bytes - source_offset);
          }
        }
        saw_gather |= gather;
        output += n;
      }
      if (!plan->split_k) break;
      k_start = (uint16_t)(k_start + k_blocks);
      if (k_start >= plan->k_blocks) break;
    }
    input += m;
  }

  qbs_command_t command;
  int has_command = 1;
  CHECK(qbs_plan_next(plan, &cursor, &command, &has_command) == QBS_STATUS_OK);
  CHECK(!has_command);
  CHECK((plan->needs_activation_gather != 0) == (saw_gather != 0));
  CHECK(plan->workspace_bytes >= partial_bytes + max_gather_bytes);
  if (!saw_gather) CHECK(plan->workspace_bytes == partial_bytes);
  return 0;
}

static int test_plan_matrix(void) {
  const uint32_t m_values[] = {1, 2, 3, 4, 5, 7, 8, 9};
  const uint32_t n_values[] = {1, 3, 4, 31, 32, 33, 35, 64};
  const uint32_t k_block_values[] = {1, 2, 255, 256, 257, 511};
  qbs_device_t device;
  CHECK(qbs_device_init_reference(1024, &device) == QBS_STATUS_OK);

  for (size_t profile_index = 0;
       profile_index < sizeof(weight_profiles) / sizeof(weight_profiles[0]);
       ++profile_index) {
    const unsigned weight_profile = weight_profiles[profile_index];
    const unsigned activation_profile =
        qbs_default_activation_profile(weight_profile);
    const uint32_t block_elements = qbs_weight_block_elements(weight_profile);
    for (unsigned weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR;
         weight_layout <= QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR; ++weight_layout) {
      for (unsigned activation_storage = QBS_ACTIVATION_STORAGE_ROW_MAJOR;
           activation_storage <= QBS_ACTIVATION_STORAGE_M4_GROUPED;
           ++activation_storage) {
        for (size_t m_index = 0;
             m_index < sizeof(m_values) / sizeof(m_values[0]); ++m_index) {
          for (size_t n_index = 0;
               n_index < sizeof(n_values) / sizeof(n_values[0]); ++n_index) {
            for (size_t k_index = 0;
                 k_index < sizeof(k_block_values) / sizeof(k_block_values[0]);
                 ++k_index) {
              const qbs_problem_t problem = {
                  .weight_profile = (uint8_t)weight_profile,
                  .activation_profile = (uint8_t)activation_profile,
                  .weight_layout = (uint8_t)weight_layout,
                  .activation_storage = (uint8_t)activation_storage,
                  .m = m_values[m_index],
                  .n = n_values[n_index],
                  .k_elements = k_block_values[k_index] * block_elements,
              };
              qbs_plan_t plan;
              CHECK(qbs_plan_create(&device, &problem, &plan) == QBS_STATUS_OK);
              CHECK(validate_plan_commands(&plan) == 0);
            }
          }
        }
      }
    }
  }
  return 0;
}

static int test_plan_and_execute(void) {
  qbs_device_t device;
  CHECK(qbs_device_init_reference(1024, &device) == QBS_STATUS_OK);

  qbs_problem_t simple = {
      .weight_profile = QBS_WEIGHT_PROFILE_Q4_K,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
      .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
      .activation_storage = QBS_ACTIVATION_STORAGE_ROW_MAJOR,
      .m = 1,
      .n = 35,
      .k_elements = 6u * QBS_Q4_K_BLOCK_ELEMENTS,
  };
  qbs_plan_t simple_plan;
  CHECK(qbs_plan_create(&device, &simple, &simple_plan) == QBS_STATUS_OK);
  CHECK(!simple_plan.split_k && simple_plan.command_n == 32);
  mock_executor_t simple_mock = {.plan = &simple_plan};
  CHECK(collect_commands(&simple_plan, &simple_mock) == 0);
  CHECK(simple_mock.command_count == 2);
  CHECK(simple_mock.commands[0].n == 32);
  CHECK(simple_mock.commands[1].n == 3);

  qbs_problem_t split = {
      .weight_profile = QBS_WEIGHT_PROFILE_Q4_0,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_0,
      .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
      .activation_storage = QBS_ACTIVATION_STORAGE_M4_GROUPED,
      .m = 6,
      .n = 7,
      .k_elements = 300u * QBS_Q4_0_BLOCK_ELEMENTS,
  };
  qbs_plan_t plan;
  CHECK(qbs_plan_create(&device, &split, &plan) == QBS_STATUS_OK);
  CHECK(plan.split_k && plan.command_k_blocks == 256);
  CHECK(plan.command_n == 4);
  CHECK(plan.workspace_bytes ==
        4u * 4u * sizeof(float) +
            2u * QBS_MAX_K_BLOCKS * QBS_Q8_0_BLOCK_BYTES);

  mock_executor_t mock = {.plan = &plan};
  CHECK(collect_commands(&plan, &mock) == 0);
  CHECK(mock.command_count == 8);
  CHECK(mock.commands[0].m == 4 &&
        mock.commands[0].activation_layout ==
            QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED);
  CHECK(mock.commands[4].m == 2 && mock.commands[4].gather_activation);

  const size_t weight_bytes = qbs_weight_storage_bytes(
      split.weight_profile, split.weight_layout, split.n, plan.k_blocks);
  const size_t activation_bytes = qbs_activation_storage_bytes(
      split.activation_profile, split.activation_storage, split.m,
      plan.k_blocks);
  uint8_t *weights = (uint8_t *)calloc(1, weight_bytes);
  uint8_t *activations = (uint8_t *)malloc(activation_bytes);
  float *output = (float *)calloc(split.m * split.n, sizeof(float));
  void *workspace = malloc(plan.workspace_bytes);
  CHECK(weights != NULL && activations != NULL && output != NULL &&
        workspace != NULL);
  const size_t activation_block_bytes =
      qbs_activation_block_bytes(split.activation_profile);
  for (size_t row = 0; row < split.m; ++row)
    for (size_t block = 0; block < plan.k_blocks; ++block)
      memset(activations + (row * plan.k_blocks + block) *
                 activation_block_bytes,
             (int)((row * 19u + block) & 0xffu), activation_block_bytes);
  mock.weights = weights;
  mock.activations = activations;
  CHECK(qbs_execute(&plan, weights, weight_bytes, activations,
                    activation_bytes, output, split.m * split.n, split.n,
                    workspace, plan.workspace_bytes, mock_execute, &mock) ==
        QBS_STATUS_OK);
  CHECK(mock.next_command == mock.command_count);
  for (size_t index = 0; index < split.m * split.n; ++index)
    CHECK(output[index] == 300.0f);

  free(workspace);
  free(output);
  free(activations);
  free(weights);
  return 0;
}

static int test_adaptive_multirow_plan(void) {
  qbs_device_t device;
  CHECK(qbs_device_init_reference(1024, &device) == QBS_STATUS_OK);

  CHECK(qbs_recommend_activation_storage(
            &device, QBS_WEIGHT_PROFILE_Q4_K,
            QBS_ACTIVATION_PROFILE_Q8_K,
            QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR, 4u, 1536u, 1536u) ==
        QBS_ACTIVATION_STORAGE_M4_GROUPED);
  CHECK(qbs_recommend_activation_storage(
            &device, QBS_WEIGHT_PROFILE_Q4_K,
            QBS_ACTIVATION_PROFILE_Q8_K,
            QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR, 8u, 1536u, 1536u) ==
        QBS_ACTIVATION_STORAGE_M8_GROUPED);
  qbs_device_t no_m8 = device;
  no_m8.capabilities.activation_layouts &=
      (uint16_t)~(UINT16_C(1) << QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED);
  CHECK(qbs_recommend_activation_storage(
            &no_m8, QBS_WEIGHT_PROFILE_Q4_K,
            QBS_ACTIVATION_PROFILE_Q8_K,
            QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR, 8u, 1536u, 1536u) ==
        QBS_ACTIVATION_STORAGE_M4_GROUPED);

  const qbs_problem_t problem = {
      .weight_profile = QBS_WEIGHT_PROFILE_Q6_K,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
      .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
      .activation_storage = QBS_ACTIVATION_STORAGE_M8_GROUPED,
      .m = 15,
      .n = 35,
      .k_elements = 6u * QBS_Q6_K_BLOCK_ELEMENTS,
  };
  qbs_plan_t plan;
  CHECK(qbs_plan_create(&device, &problem, &plan) == QBS_STATUS_OK);
  CHECK(plan.uses_wide_m);
  CHECK(plan.command_m == 8u);
  CHECK(plan.command_n == 32u);
  CHECK(plan.wide_command_n == 16u);
  CHECK(!plan.split_k && !plan.needs_activation_gather);

  mock_executor_t mock = {.plan = &plan};
  CHECK(collect_commands(&plan, &mock) == 0);
  CHECK(mock.command_count == 6u);
  for (unsigned index = 0; index < 6u; ++index) {
    const qbs_command_t *command = &mock.commands[index];
    CHECK(command->m == (index < 3u ? 8u : 7u));
    CHECK(command->n == (index % 3u == 2u ? 3u : 16u));
    CHECK(command->activation_layout ==
          QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED);
    CHECK(!command->gather_activation);
    CHECK((size_t)command->m * command->n <= QBS_MAX_RESULTS);
  }
  CHECK(mock.commands[3].input_start == 8u);
  CHECK(mock.commands[3].activation_offset_bytes ==
        8u * plan.k_blocks * QBS_Q8_K_BLOCK_BYTES);
  CHECK(validate_plan_commands(&plan) == 0);

  qbs_problem_t mixed_tail = problem;
  mixed_tail.m = 12u;
  CHECK(qbs_plan_create(&device, &mixed_tail, &plan) == QBS_STATUS_OK);
  memset(&mock, 0, sizeof(mock));
  mock.plan = &plan;
  CHECK(collect_commands(&plan, &mock) == 0);
  CHECK(mock.command_count == 5u);
  CHECK(mock.commands[0].m == 8u && mock.commands[0].n == 16u);
  CHECK(mock.commands[3].m == 4u && mock.commands[3].n == 32u);
  CHECK(mock.commands[3].activation_layout ==
        QBS_ACTIVATION_LAYOUT_ROW_MAJOR);
  CHECK(validate_plan_commands(&plan) == 0);

  qbs_problem_t split_k = problem;
  split_k.k_elements = 257u * QBS_Q6_K_BLOCK_ELEMENTS;
  CHECK(qbs_plan_create(&device, &split_k, &plan) == QBS_STATUS_SHAPE);

  qbs_problem_t wrong_storage = problem;
  wrong_storage.m = 4u;
  CHECK(qbs_plan_create(&device, &wrong_storage, &plan) == QBS_STATUS_LAYOUT);
  return 0;
}

static int test_activation_context_execution(void) {
  qbs_device_t device;
  CHECK(qbs_device_init_reference(1024, &device) == QBS_STATUS_OK);

  const qbs_problem_t problem = {
      .weight_profile = QBS_WEIGHT_PROFILE_Q4_K,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
      .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
      .activation_storage = QBS_ACTIVATION_STORAGE_ROW_MAJOR,
      .m = 1,
      .n = 65,
      .k_elements = 6u * QBS_Q4_K_BLOCK_ELEMENTS,
  };
  qbs_plan_t plan;
  CHECK(qbs_plan_create(&device, &problem, &plan) == QBS_STATUS_OK);
  CHECK(qbs_plan_supports_activation_context(&plan));
  CHECK(plan.activation_context_count == 1u);
  CHECK(plan.activation_context_generation_bits == 8u);

  mock_executor_t mock = {
      .plan = &plan,
      .expect_activation_context = 1u,
      .expected_token = {.context_id = 0u, .generation = 0xa5u},
  };
  CHECK(collect_commands(&plan, &mock) == 0);
  CHECK(mock.command_count == 3u);
  CHECK(mock.commands[0].n == 32u && mock.commands[1].n == 32u &&
        mock.commands[2].n == 1u);

  const size_t weight_bytes = qbs_weight_storage_bytes(
      problem.weight_profile, problem.weight_layout, problem.n,
      plan.k_blocks);
  const size_t activation_bytes = qbs_activation_storage_bytes(
      problem.activation_profile, problem.activation_storage, problem.m,
      plan.k_blocks);
  uint8_t *weights = (uint8_t *)calloc(1, weight_bytes);
  uint8_t *activations = (uint8_t *)calloc(1, activation_bytes);
  float *output = (float *)calloc(problem.n, sizeof(float));
  CHECK(weights != NULL && activations != NULL && output != NULL);
  mock.weights = weights;
  mock.activations = activations;

  const qbs_execution_options_t options = {
      .use_activation_context = 1u,
      .activation_context = mock.expected_token,
  };
  CHECK(qbs_execute_with_options(
            &plan, weights, weight_bytes, activations, activation_bytes,
            output, problem.n, problem.n, NULL, 0u, &options, mock_execute,
            &mock) == QBS_STATUS_OK);
  CHECK(mock.next_command == 3u);
  CHECK(mock.observed_activation_access[0] == QBS_ACTIVATION_ACCESS_FILL);
  CHECK(mock.observed_activation_access[1] == QBS_ACTIVATION_ACCESS_REUSE);
  CHECK(mock.observed_activation_access[2] == QBS_ACTIVATION_ACCESS_RELEASE);
  for (size_t index = 0; index < problem.n; ++index)
    CHECK(output[index] == 6.0f);

  static const uint8_t expected_scoped_access[3][3] = {
      {QBS_ACTIVATION_ACCESS_FILL, QBS_ACTIVATION_ACCESS_REUSE,
       QBS_ACTIVATION_ACCESS_REUSE},
      {QBS_ACTIVATION_ACCESS_REUSE, QBS_ACTIVATION_ACCESS_REUSE,
       QBS_ACTIVATION_ACCESS_REUSE},
      {QBS_ACTIVATION_ACCESS_REUSE, QBS_ACTIVATION_ACCESS_REUSE,
       QBS_ACTIVATION_ACCESS_RELEASE},
  };
  for (uint8_t scope = QBS_ACTIVATION_CONTEXT_SCOPE_FILL_KEEP;
       scope <= QBS_ACTIVATION_CONTEXT_SCOPE_REUSE_RELEASE; ++scope) {
    qbs_execution_options_t scoped_options = options;
    scoped_options.activation_context_scope = scope;
    mock.next_command = 0u;
    mock.activation_context_scope = scope;
    memset(mock.observed_activation_access, 0xff,
           sizeof(mock.observed_activation_access));
    CHECK(qbs_execute_with_options(
              &plan, weights, weight_bytes, activations, activation_bytes,
              output, problem.n, problem.n, NULL, 0u, &scoped_options,
              mock_execute, &mock) == QBS_STATUS_OK);
    CHECK(mock.next_command == 3u);
    for (size_t index = 0; index < 3u; ++index)
      CHECK(mock.observed_activation_access[index] ==
            expected_scoped_access[scope - 1u][index]);
  }

  qbs_execution_options_t bad_scope_options = options;
  bad_scope_options.activation_context_scope = 4u;
  mock.next_command = 0u;
  CHECK(qbs_execute_with_options(
            &plan, weights, weight_bytes, activations, activation_bytes,
            output, problem.n, problem.n, NULL, 0u, &bad_scope_options,
            mock_execute, &mock) == QBS_STATUS_BAD_ARGUMENT);
  CHECK(mock.next_command == 0u);

  mock.next_command = 0u;
  mock.expect_activation_context = 0u;
  mock.activation_context_scope = QBS_ACTIVATION_CONTEXT_SCOPE_OPERATION;
  memset(mock.observed_activation_access, 0xff,
         sizeof(mock.observed_activation_access));
  CHECK(qbs_execute(&plan, weights, weight_bytes, activations,
                    activation_bytes, output, problem.n, problem.n, NULL, 0u,
                    mock_execute, &mock) == QBS_STATUS_OK);
  CHECK(mock.next_command == 3u);
  for (size_t index = 0; index < 3u; ++index)
    CHECK(mock.observed_activation_access[index] ==
          QBS_ACTIVATION_ACCESS_DIRECT);

  qbs_execution_options_t invalid_options = options;
  invalid_options.activation_context.context_id = 1u;
  mock.next_command = 0u;
  CHECK(qbs_execute_with_options(
            &plan, weights, weight_bytes, activations, activation_bytes,
            output, problem.n, problem.n, NULL, 0u, &invalid_options,
            mock_execute, &mock) == QBS_STATUS_CONTEXT_TOKEN);
  CHECK(mock.next_command == 0u);

  qbs_plan_t narrow_generation_plan = plan;
  narrow_generation_plan.activation_context_generation_bits = 4u;
  invalid_options = options;
  invalid_options.activation_context.generation = 16u;
  CHECK(qbs_execute_with_options(
            &narrow_generation_plan, weights, weight_bytes, activations,
            activation_bytes, output, problem.n, problem.n, NULL, 0u,
            &invalid_options, mock_execute, &mock) ==
        QBS_STATUS_CONTEXT_TOKEN);
  CHECK(mock.next_command == 0u);

  qbs_problem_t single_tile_problem = problem;
  single_tile_problem.n = 32u;
  qbs_plan_t single_tile_plan;
  CHECK(qbs_plan_create(&device, &single_tile_problem, &single_tile_plan) ==
        QBS_STATUS_OK);
  CHECK(!qbs_plan_supports_activation_context(&single_tile_plan));
  CHECK(qbs_execute_with_options(
            &single_tile_plan, weights, weight_bytes, activations,
            activation_bytes, output, problem.n, problem.n, NULL, 0u,
            &options, mock_execute, &mock) ==
        QBS_STATUS_CONTEXT_UNSUPPORTED);
  CHECK(mock.next_command == 0u);

  free(output);
  free(activations);
  free(weights);
  return 0;
}

static int test_restricted_row_major_device(void) {
  qbs_device_t device;
  CHECK(qbs_device_init_reference(1024, &device) == QBS_STATUS_OK);
  device.capabilities.max_m = 2;
  device.capabilities.max_n = 7;
  device.capabilities.max_k_blocks = 3;
  device.capabilities.weight_layouts =
      (uint16_t)(UINT16_C(1) << QBS_WEIGHT_LAYOUT_ROW_MAJOR);
  device.capabilities.activation_layouts =
      (uint16_t)(UINT16_C(1) << QBS_ACTIVATION_LAYOUT_ROW_MAJOR);

  const qbs_problem_t problem = {
      .weight_profile = QBS_WEIGHT_PROFILE_Q4_0,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_0,
      .weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR,
      .activation_storage = QBS_ACTIVATION_STORAGE_ROW_MAJOR,
      .m = 5,
      .n = 3,
      .k_elements = 7u * QBS_Q4_0_BLOCK_ELEMENTS,
  };
  qbs_plan_t plan;
  CHECK(qbs_plan_create(&device, &problem, &plan) == QBS_STATUS_OK);
  CHECK(plan.command_m == 2);
  CHECK(plan.command_n == 1);
  CHECK(plan.command_k_blocks == 3);
  CHECK(plan.split_k && plan.needs_activation_gather);
  CHECK(plan.workspace_bytes ==
        2u * sizeof(float) + 2u * 3u * QBS_Q8_0_BLOCK_BYTES);

  mock_executor_t mock = {.plan = &plan};
  CHECK(collect_commands(&plan, &mock) == 0);
  CHECK(mock.command_count == 27);
  CHECK(mock.commands[0].m == 2 && mock.commands[0].n == 1 &&
        mock.commands[0].k_blocks == 3 &&
        mock.commands[0].gather_activation);
  CHECK(mock.commands[21].m == 1 &&
        mock.commands[21].k_block_start == 3 &&
        mock.commands[21].gather_activation);
  CHECK(mock.commands[mock.command_count - 1].m == 1 &&
        mock.commands[mock.command_count - 1].k_blocks == 1 &&
        !mock.commands[mock.command_count - 1].gather_activation);

  const size_t weight_bytes = qbs_weight_storage_bytes(
      problem.weight_profile, problem.weight_layout, problem.n,
      plan.k_blocks);
  const size_t activation_bytes = qbs_activation_storage_bytes(
      problem.activation_profile, problem.activation_storage, problem.m,
      plan.k_blocks);
  const size_t output_elements = problem.m * problem.n;
  uint8_t *weights = (uint8_t *)calloc(1, weight_bytes + 1u);
  uint8_t *activations = (uint8_t *)malloc(activation_bytes + 1u);
  float *output = (float *)calloc(output_elements, sizeof(float));
  void *workspace = malloc(plan.workspace_bytes);
  CHECK(weights != NULL && activations != NULL && output != NULL &&
        workspace != NULL);
  const size_t activation_block_bytes =
      qbs_activation_block_bytes(problem.activation_profile);
  for (size_t row = 0; row < problem.m; ++row) {
    for (size_t block = 0; block < plan.k_blocks; ++block) {
      memset(activations + (row * plan.k_blocks + block) *
                 activation_block_bytes,
             (int)((row * 23u + block) & 0xffu), activation_block_bytes);
    }
  }
  mock.weights = weights;
  mock.activations = activations;

  CHECK(qbs_execute(&plan, weights, weight_bytes - 1u, activations,
                    activation_bytes, output, output_elements, problem.n,
                    workspace, plan.workspace_bytes, mock_execute, &mock) ==
        QBS_STATUS_BUFFER_TOO_SMALL);
  CHECK(mock.next_command == 0);
  CHECK(qbs_execute(&plan, weights, weight_bytes, activations,
                    activation_bytes, output, output_elements - 1u,
                    problem.n, workspace, plan.workspace_bytes,
                    mock_execute, &mock) == QBS_STATUS_BUFFER_TOO_SMALL);
  CHECK(mock.next_command == 0);
  CHECK(qbs_execute(&plan, weights + 1u, weight_bytes, activations,
                    activation_bytes, output, output_elements, problem.n,
                    workspace, plan.workspace_bytes, mock_execute, &mock) ==
        QBS_STATUS_BUFFER_ALIGNMENT);
  CHECK(mock.next_command == 0);
  CHECK(qbs_execute(&plan, weights, weight_bytes, activations + 1u,
                    activation_bytes, output, output_elements, problem.n,
                    workspace, plan.workspace_bytes, mock_execute, &mock) ==
        QBS_STATUS_BUFFER_ALIGNMENT);
  CHECK(mock.next_command == 0);
  uint8_t *misaligned_output =
      (uint8_t *)malloc(output_elements * sizeof(float) + _Alignof(float));
  CHECK(misaligned_output != NULL);
  CHECK(qbs_execute(&plan, weights, weight_bytes, activations, activation_bytes,
                    (float *)(void *)(misaligned_output + 1u), output_elements,
                    problem.n, workspace, plan.workspace_bytes, mock_execute,
                    &mock) == QBS_STATUS_BUFFER_ALIGNMENT);
  CHECK(mock.next_command == 0);
  free(misaligned_output);
  CHECK(qbs_execute(&plan, weights, weight_bytes, activations,
                    activation_bytes, output, output_elements, problem.n,
                    workspace, plan.workspace_bytes, mock_execute, &mock) ==
        QBS_STATUS_OK);
  CHECK(mock.next_command == mock.command_count);
  for (size_t index = 0; index < output_elements; ++index)
    CHECK(output[index] == 7.0f);

  free(workspace);
  free(output);
  free(activations);
  free(weights);
  return 0;
}

static int test_workspace_sizing(void) {
  qbs_device_t device;
  CHECK(qbs_device_init_reference(1024, &device) == QBS_STATUS_OK);

  qbs_problem_t problem = {
      .weight_profile = QBS_WEIGHT_PROFILE_Q4_K,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
      .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
      .activation_storage = QBS_ACTIVATION_STORAGE_ROW_MAJOR,
      .m = 1,
      .n = 35,
      .k_elements = 300u * QBS_Q4_K_BLOCK_ELEMENTS,
  };
  qbs_plan_t plan;
  CHECK(qbs_plan_create(&device, &problem, &plan) == QBS_STATUS_OK);
  CHECK(plan.split_k && !plan.needs_activation_gather);
  CHECK(plan.workspace_bytes == 4u * sizeof(float));

  problem.activation_storage = QBS_ACTIVATION_STORAGE_M4_GROUPED;
  problem.m = 4;
  CHECK(qbs_plan_create(&device, &problem, &plan) == QBS_STATUS_OK);
  CHECK(plan.split_k && !plan.needs_activation_gather);
  CHECK(plan.workspace_bytes == 4u * 4u * sizeof(float));

  problem.m = 5;
  CHECK(qbs_plan_create(&device, &problem, &plan) == QBS_STATUS_OK);
  CHECK(plan.split_k && !plan.needs_activation_gather);
  CHECK(plan.workspace_bytes == 4u * 4u * sizeof(float));

  problem.m = 6;
  CHECK(qbs_plan_create(&device, &problem, &plan) == QBS_STATUS_OK);
  CHECK(plan.needs_activation_gather);
  CHECK(plan.workspace_bytes ==
        4u * 4u * sizeof(float) +
            2u * QBS_MAX_K_BLOCKS * QBS_Q8_K_BLOCK_BYTES);

  CHECK(qbs_device_init_reference(1024, &device) == QBS_STATUS_OK);
  device.capabilities.max_m = 1;
  problem.weight_profile = QBS_WEIGHT_PROFILE_Q4_0;
  problem.activation_profile = QBS_ACTIVATION_PROFILE_Q8_0;
  problem.weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR;
  problem.activation_storage = QBS_ACTIVATION_STORAGE_M4_GROUPED;
  problem.m = 3;
  problem.n = 4;
  problem.k_elements = QBS_Q4_0_BLOCK_ELEMENTS;
  CHECK(qbs_plan_create(&device, &problem, &plan) == QBS_STATUS_OK);
  CHECK(!plan.split_k && plan.needs_activation_gather);
  CHECK(plan.workspace_bytes == QBS_Q8_0_BLOCK_BYTES);
  return 0;
}

static int test_non_split_alignment_gather(void) {
  qbs_device_t device;
  CHECK(qbs_device_init_reference(1024, &device) == QBS_STATUS_OK);
  device.capabilities.max_m = 1;
  device.capabilities.max_n = 4;
  device.capabilities.weight_layouts =
      (uint16_t)(UINT16_C(1) << QBS_WEIGHT_LAYOUT_ROW_MAJOR);
  device.capabilities.activation_layouts =
      (uint16_t)(UINT16_C(1) << QBS_ACTIVATION_LAYOUT_ROW_MAJOR);

  const qbs_problem_t problem = {
      .weight_profile = QBS_WEIGHT_PROFILE_Q4_0,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_0,
      .weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR,
      .activation_storage = QBS_ACTIVATION_STORAGE_ROW_MAJOR,
      .m = 2,
      .n = 1,
      .k_elements = QBS_Q4_0_BLOCK_ELEMENTS,
  };
  qbs_plan_t plan;
  CHECK(qbs_plan_create(&device, &problem, &plan) == QBS_STATUS_OK);
  CHECK(!plan.split_k && plan.needs_activation_gather);
  CHECK(plan.workspace_bytes == QBS_Q8_0_BLOCK_BYTES);

  mock_executor_t mock = {.plan = &plan};
  CHECK(collect_commands(&plan, &mock) == 0);
  CHECK(mock.command_count == 2);
  CHECK(!mock.commands[0].gather_activation);
  CHECK(mock.commands[1].gather_activation);

  const size_t weight_bytes = qbs_weight_storage_bytes(
      problem.weight_profile, problem.weight_layout, problem.n,
      plan.k_blocks);
  const size_t activation_bytes = qbs_activation_storage_bytes(
      problem.activation_profile, problem.activation_storage, problem.m,
      plan.k_blocks);
  uint8_t *weights = (uint8_t *)calloc(1, weight_bytes);
  uint8_t *activations = (uint8_t *)calloc(1, activation_bytes);
  float output[2] = {0.0f, 0.0f};
  void *workspace = malloc(plan.workspace_bytes);
  CHECK(weights != NULL && activations != NULL && workspace != NULL);
  mock.weights = weights;
  mock.activations = activations;
  CHECK(qbs_execute(&plan, weights, weight_bytes, activations,
                    activation_bytes, output, 2, 1, workspace,
                    plan.workspace_bytes, mock_execute, &mock) ==
        QBS_STATUS_OK);
  CHECK(output[0] == 1.0f && output[1] == 1.0f);

  free(workspace);
  free(activations);
  free(weights);
  return 0;
}

int main(void) {
  CHECK(test_device_and_profiles() == 0);
  CHECK(test_weight_repack() == 0);
  CHECK(test_activation_pack_profile(QBS_ACTIVATION_PROFILE_Q8_K) == 0);
  CHECK(test_activation_pack_profile(QBS_ACTIVATION_PROFILE_Q8_0) == 0);
  CHECK(test_activation_pack_m8_profile(QBS_ACTIVATION_PROFILE_Q8_K, 8u) == 0);
  CHECK(test_activation_pack_m8_profile(QBS_ACTIVATION_PROFILE_Q8_K, 15u) == 0);
  CHECK(test_activation_pack_m8_profile(QBS_ACTIVATION_PROFILE_Q8_0, 7u) == 0);
  CHECK(test_plan_matrix() == 0);
  CHECK(test_plan_and_execute() == 0);
  CHECK(test_adaptive_multirow_plan() == 0);
  CHECK(test_activation_context_execution() == 0);
  CHECK(test_restricted_row_major_device() == 0);
  CHECK(test_non_split_alignment_gather() == 0);
  CHECK(test_workspace_sizing() == 0);
  puts("QBS runtime-neutral profile, layout, planner, and executor: PASS");
  return 0;
}
