#include <assert.h>
#include <stdio.h>
#include "qbs/qbs.h"
#include "qbs_ref.h"

static uint64_t info(void *context, unsigned index) {
  (void)context;
  return qbs_ref_capability_word(index, 1024);
}

int main(void) {
  qbs_device_t device;
  assert(qbs_device_query(info, NULL, &device) == QBS_STATUS_OK);
  unsigned plans = 0, commands = 0;
  for (unsigned n = 32; n <= 128; n += 32) {
    for (unsigned mode = 4; mode <= 8; mode += 4) {
      const qbs_problem_t problem = {
        .weight_profile = QBS_WEIGHT_PROFILE_Q4_K,
        .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
        .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
        .activation_storage = mode == 8 ? QBS_ACTIVATION_STORAGE_M8_GROUPED
                                       : QBS_ACTIVATION_STORAGE_M4_GROUPED,
        .m = 8, .n = n, .k_elements = 2048,
      };
      qbs_plan_t plan;
      assert(qbs_plan_create(&device, &problem, &plan) == QBS_STATUS_OK);
      assert(!plan.split_k && !plan.needs_activation_gather && !plan.workspace_bytes);
      assert(plan.command_m == mode && plan.command_n == 32 && plan.wide_command_n == 16);
      assert(plan.k_blocks == 8 && !qbs_plan_supports_activation_context(&plan));
      unsigned seen[8*128] = {0}, count = 0;
      qbs_plan_cursor_t cursor;
      qbs_plan_cursor_reset(&cursor);
      for (;;) {
        qbs_command_t command;
        int has_command;
        assert(qbs_plan_next(&plan, &cursor, &command, &has_command) == QBS_STATUS_OK);
        if (!has_command) break;
        assert(command.m == mode && command.n == (mode == 8 ? 16 : 32));
        assert(command.k_blocks == 8 && command.k_block_start == 0 &&
               !command.accumulate && !command.gather_activation);
        assert(command.activation_layout == (mode == 8 ? QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED
                                                       : QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED));
        for (unsigned row = 0; row < command.m; ++row)
          for (unsigned col = 0; col < command.n; ++col) {
            const size_t index = command.output_offset_elements + row*n + col;
            assert(index < 8*n && !seen[index]);
            seen[index] = 1;
          }
        ++count;
      }
      for (unsigned i = 0; i < 8*n; ++i) assert(seen[i] == 1);
      assert(count == n/16);
      commands += count;
      ++plans;
    }
  }
  printf("STAGE2_PROJECTION_PLAN_PASS plans=%u commands=%u\n", plans, commands);
  return 0;
}
