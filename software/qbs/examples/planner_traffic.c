#include "qbs/qbs.h"

#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>

#define REQUIRE(condition) do { \
  if (!(condition)) { \
    fprintf(stderr, "traffic audit failed at line %d\n", __LINE__); \
    exit(EXIT_FAILURE); \
  } \
} while (0)

/* Logical payload demanded by the production planner, not AXI beats, DDR
 * traffic, cycle measurements or a cache model. No tensors are executed. */
static void audit(const qbs_device_t *device, unsigned profile, unsigned m,
                  unsigned n, unsigned k, unsigned segment, int adaptive) {
  const unsigned activation = qbs_default_activation_profile(profile);
  qbs_weight_profile_info_t wi;
  qbs_activation_profile_info_t ai;
  REQUIRE(qbs_weight_profile_info(profile, &wi) == QBS_STATUS_OK);
  REQUIRE(qbs_activation_profile_info(activation, &ai) == QBS_STATUS_OK);
  const unsigned storage = adaptive
      ? qbs_recommend_activation_storage(device, profile, activation,
          QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR, m, n, k)
      : (m >= 4 ? QBS_ACTIVATION_STORAGE_M4_GROUPED
                : QBS_ACTIVATION_STORAGE_ROW_MAJOR);
  const qbs_problem_t problem = {
    .weight_profile = profile, .activation_profile = activation,
    .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
    .activation_storage = storage, .m = m, .n = n, .k_elements = k,
  };
  qbs_plan_t plan;
  REQUIRE((segment == 0 ? qbs_plan_create(device, &problem, &plan)
      : qbs_plan_create_segmented_r4(device, &problem, segment, &plan))
      == QBS_STATUS_OK);
  qbs_plan_cursor_t cursor;
  qbs_plan_cursor_reset(&cursor);
  uint64_t commands = 0, weight = 0, activation_direct = 0, macs = 0;
  unsigned input_tiles = 0, previous_input = UINT32_MAX;
  for (;;) {
    qbs_command_t command;
    int present;
    REQUIRE(qbs_plan_next(&plan, &cursor, &command, &present) == QBS_STATUS_OK);
    if (!present) break;
    ++commands;
    if (command.input_start != previous_input) {
      previous_input = command.input_start;
      ++input_tiles;
    }
    REQUIRE(command.input_start + command.m <= m);
    REQUIRE(command.output_start + command.n <= n);
    REQUIRE(command.k_block_start + command.k_blocks <= plan.k_blocks);
    weight += (uint64_t)command.n * command.k_blocks * wi.block_bytes;
    const unsigned stored_m = command.activation_layout ==
        QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED ? QBS_MAX_M : command.m;
    activation_direct += (uint64_t)stored_m * command.k_blocks * ai.block_bytes;
    macs += (uint64_t)command.m * command.n * command.k_blocks * wi.block_elements;
  }
  const uint64_t weight_once = (uint64_t)n * plan.k_blocks * wi.block_bytes;
  REQUIRE(weight == weight_once * input_tiles);
  REQUIRE(macs == (uint64_t)m * n * k);
  const int context = qbs_plan_supports_activation_context(&plan);
  const uint64_t activation_operation = context
      ? (uint64_t)m * plan.k_blocks * ai.block_bytes : activation_direct;
  if (profile == QBS_WEIGHT_PROFILE_Q4_K && m == 32 && n == 1536 && k == 1536) {
    REQUIRE(commands == 384);
    REQUIRE(weight == (adaptive ? UINT64_C(5308416) : UINT64_C(10616832)));
    REQUIRE(activation_direct == (adaptive ? UINT64_C(5382144) : UINT64_C(2691072)));
  }
  if (profile == QBS_WEIGHT_PROFILE_Q8_0_WEIGHT && m == 4 && n == 1536 && k == 8960) {
    REQUIRE(commands == (segment ? 96 : 768));
    REQUIRE(weight == UINT64_C(14622720));
    REQUIRE(activation_direct == (segment ? UINT64_C(1827840) : UINT64_C(14622720)));
  }
  printf("%s,%u,%u,%u,%u,%s,%u,%" PRIu64 ",%u,%" PRIu64
         ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%d,%" PRIu64 "\n",
         qbs_weight_profile_name(profile), m, n, k, segment,
         adaptive ? "adaptive" : "m4", storage, commands, input_tiles,
         weight_once, weight, activation_direct, activation_operation, context, macs);
}

int main(void) {
  qbs_device_t device;
  REQUIRE(qbs_device_init_reference(1024, &device) == QBS_STATUS_OK);
  const unsigned profiles[] = {QBS_WEIGHT_PROFILE_Q4_K, QBS_WEIGHT_PROFILE_Q8_0_WEIGHT};
  const unsigned rows[] = {1, 4, 8, 16, 32};
  /* Projection dimensions from the Qwen2.5-1.5B workload; M is a shape sweep,
   * not a claim that these are new captured Prefill activations. */
  const unsigned shapes[][2] = {{1536, 1536}, {8960, 1536}, {1536, 8960}, {37, 1536}};
  puts("profile,m,n,k,segment,policy,storage,commands,input_tiles,weight_once_bytes,"
       "weight_logical_bytes,activation_direct_bytes,activation_operation_bytes,"
       "context_eligible,macs");
  for (size_t p = 0; p < sizeof(profiles) / sizeof(profiles[0]); ++p)
    for (size_t s = 0; s < sizeof(shapes) / sizeof(shapes[0]); ++s)
      for (size_t r = 0; r < sizeof(rows) / sizeof(rows[0]); ++r)
        for (unsigned segment = 0; segment <= 256; segment += 256)
          for (int adaptive = 0; adaptive <= 1; ++adaptive)
            audit(&device, profiles[p], rows[r], shapes[s][0], shapes[s][1], segment, adaptive);
  return 0;
}
