#include "qbs/qbs.h"
#include <stdio.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL line=%d\n", __LINE__); return 1; } } while (0)

int main(void) {
    qbs_device_t device;
    CHECK(qbs_device_init_reference(1024, &device) == QBS_STATUS_OK);
    CHECK(device.capabilities.activation_context_capacity_bytes == 4672);
    for (unsigned k = 512; k <= 1536; k += 512) {
        qbs_problem_t problem = {
            .weight_profile = QBS_WEIGHT_PROFILE_Q4_K,
            .activation_profile = QBS_ACTIVATION_PROFILE_Q8_K,
            .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
            .activation_storage = QBS_ACTIVATION_STORAGE_M4_GROUPED,
            .m = 4, .n = 1536, .k_elements = k,
        };
        qbs_plan_t plan;
        CHECK(qbs_plan_create(&device, &problem, &plan) == QBS_STATUS_OK);
        CHECK(!plan.split_k && !plan.needs_activation_gather);
        unsigned bytes = 4 * (k / 256) * 292;
        CHECK(qbs_plan_supports_activation_context(&plan) == (bytes <= 4672));
        qbs_plan_cursor_t cursor;
        qbs_plan_cursor_reset(&cursor);
        unsigned commands = 0;
        for (;;) {
            qbs_command_t command;
            int present;
            CHECK(qbs_plan_next(&plan, &cursor, &command, &present) == QBS_STATUS_OK);
            if (!present) break;
            CHECK(command.m == 4 && command.n == 32 && command.k_blocks == k / 256);
            ++commands;
        }
        CHECK(commands == 48);
        printf("PLAN m=4 n=1536 k=%u activation_bytes=%u context_eligible=%d commands=%u\n",
               k, bytes, qbs_plan_supports_activation_context(&plan), commands);
    }
    return 0;
}
