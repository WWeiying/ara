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

static int test_device_and_profiles(void) {
  qbs_device_t device;
  CHECK(qbs_device_init_reference(1024, &device) == QBS_STATUS_OK);
  CHECK(device.capabilities.valid);
  CHECK(device.capabilities.max_m == 4);
  CHECK(device.capabilities.max_n == 32);
  CHECK(device.capabilities.max_k_blocks == 256);
  CHECK(device.capabilities.blocking_completion);
  CHECK(device.capabilities.fault_atomic_destination);
  CHECK(device.capabilities.requires_vstart_zero);
  CHECK(device.capabilities.idempotent_memory_only);
  CHECK(device.capabilities.requires_accelerator_consistency);

  const unsigned profiles[] = {
      QBS_WEIGHT_PROFILE_Q2_K,
      QBS_WEIGHT_PROFILE_Q3_K,
      QBS_WEIGHT_PROFILE_Q4_K,
      QBS_WEIGHT_PROFILE_Q5_K,
      QBS_WEIGHT_PROFILE_Q6_K,
      QBS_WEIGHT_PROFILE_Q4_0,
      QBS_WEIGHT_PROFILE_Q5_0,
      QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
      QBS_WEIGHT_PROFILE_IQ4_NL,
  };
  for (size_t index = 0; index < sizeof(profiles) / sizeof(profiles[0]);
       ++index) {
    qbs_weight_profile_info_t weight;
    CHECK(qbs_weight_profile_info(profiles[index], &weight) == QBS_STATUS_OK);
    const unsigned activation = qbs_default_activation_profile(weight.id);
    qbs_activation_profile_info_t activation_info;
    CHECK(qbs_activation_profile_info(activation, &activation_info) ==
          QBS_STATUS_OK);
    CHECK(weight.block_elements == activation_info.block_elements);
    CHECK(strcmp(qbs_weight_profile_name(weight.id), "invalid") != 0);
    CHECK(strcmp(qbs_activation_profile_name(activation), "invalid") != 0);
    CHECK((weight.compatible_activation_profiles &
           (UINT16_C(1) << activation)) != 0);
    CHECK(qbs_device_supports_profile(&device, weight.id, activation));
  }
  CHECK(strcmp(qbs_weight_profile_name(15), "invalid") == 0);
  CHECK(strcmp(qbs_activation_profile_name(15), "invalid") == 0);
  CHECK(qbs_weight_profile_info(15, &(qbs_weight_profile_info_t){0}) ==
        QBS_STATUS_PROFILE);
  CHECK(!qbs_device_supports_profile(
      &device, QBS_WEIGHT_PROFILE_Q4_K, QBS_ACTIVATION_PROFILE_Q8_0));

  qbs_capabilities_t caps;
  uint64_t info0 = qbs_capability_word(0, 1024);
  const uint64_t info1 = qbs_capability_word(1, 1024);
  CHECK(qbs_capabilities_decode(info0, info1, &caps) == QBS_STATUS_OK);
  info0 &= ~(UINT64_C(1) << 44);
  CHECK(qbs_capabilities_decode(info0, info1, &caps) ==
        QBS_STATUS_CAPABILITY);
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

  uint8_t *source = (uint8_t *)malloc(source_bytes);
  uint8_t *destination = (uint8_t *)malloc(destination_bytes);
  CHECK(source != NULL && destination != NULL);
  for (size_t block = 0; block < n * k_blocks; ++block)
    memset(source + block * block_bytes, (int)(block + 1u), block_bytes);
  CHECK(qbs_repack_weight_r4(QBS_WEIGHT_PROFILE_Q4_0, source, source_bytes,
                             n, k_blocks, destination, destination_bytes) ==
        QBS_STATUS_OK);
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

typedef struct {
  const qbs_plan_t *plan;
  const uint8_t *weights;
  const uint8_t *activations;
  qbs_command_t commands[128];
  size_t command_count;
  size_t next_command;
} mock_executor_t;

static qbs_status_t mock_execute(
    void *opaque, const qbs_descriptor_v1_t *descriptor, unsigned m,
    const void *activations, float *output, size_t output_stride,
    unsigned n, int segmented) {
  mock_executor_t *mock = (mock_executor_t *)opaque;
  if (mock->next_command >= mock->command_count)
    return QBS_STATUS_EXECUTION;
  const qbs_command_t *command = &mock->commands[mock->next_command++];
  const qbs_descriptor_fields_t fields =
      qbs_unpack_descriptor_header(descriptor->header);
  if (m != command->m || n != command->n ||
      fields.weight_profile != mock->plan->problem.weight_profile ||
      fields.activation_profile != mock->plan->problem.activation_profile ||
      fields.weight_layout != mock->plan->problem.weight_layout ||
      fields.activation_layout != command->activation_layout ||
      fields.k_blocks != command->k_blocks ||
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
  CHECK(plan.command_n == 4 && plan.workspace_bytes > 0);

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
  CHECK(test_plan_and_execute() == 0);
  CHECK(test_restricted_row_major_device() == 0);
  CHECK(test_non_split_alignment_gather() == 0);
  puts("QBS runtime-neutral profile, layout, planner, and executor: PASS");
  return 0;
}
