/* Host-only regression: planner limits are not emitted command dimensions. */
#include "qbs/qbs.h"
#include <stdio.h>

int main(void) {
    qbs_device_t device;
    qbs_plan_t plan;
    const qbs_problem_t problem = {
        .weight_profile = QBS_WEIGHT_PROFILE_Q4_K,
        .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
        .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
        .activation_storage = QBS_ACTIVATION_STORAGE_ROW_MAJOR,
        .m = 1, .n = 32, .k_elements = 1536,
    };
    if (qbs_device_init_reference(1024, &device) != QBS_STATUS_OK ||
        qbs_plan_create(&device, &problem, &plan) != QBS_STATUS_OK ||
        plan.command_m != 4 || plan.command_k_blocks != 256 ||
        plan.workspace_bytes || plan.split_k) return 1;
    qbs_plan_cursor_t cursor;
    qbs_command_t command;
    int has_command;
    qbs_plan_cursor_reset(&cursor);
    if (qbs_plan_next(&plan, &cursor, &command, &has_command) != QBS_STATUS_OK ||
        !has_command || command.m != 1 || command.n != 32 || command.k_blocks != 6 ||
        command.input_start || command.output_start || command.k_block_start ||
        command.accumulate || command.gather_activation) return 1;
    if (qbs_plan_next(&plan, &cursor, &command, &has_command) != QBS_STATUS_OK ||
        has_command) return 1;
    puts("HOST_PLAN limits_M=4 limits_K_blocks=256 emitted_M=1 emitted_K_blocks=6 commands=1");
    return 0;
}
