#include "qbs/qbs.h"

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#define CHECK(x) do { if (!(x)) { \
  fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); return 1; \
} } while (0)

/* The pre-fix full scan is intentionally independent of the bounded selector. */
static bool full_scan(const qbs_plan_t *plan, const qbs_capabilities_t *caps) {
  const uint8_t required_modes =
      (uint8_t)((UINT8_C(1) << QBS_ACTIVATION_ACCESS_FILL) |
                (UINT8_C(1) << QBS_ACTIVATION_ACCESS_REUSE) |
                (UINT8_C(1) << QBS_ACTIVATION_ACCESS_RELEASE));
  if (plan->split_k || plan->needs_activation_gather ||
      caps->activation_context_count == 0u ||
      caps->activation_context_generation_bits == 0u ||
      caps->activation_context_generation_bits > 8u ||
      caps->activation_context_capacity_bytes == 0u ||
      (caps->activation_context_access_modes & required_modes) != required_modes ||
      (caps->activation_context_profiles &
       (UINT16_C(1) << plan->problem.activation_profile)) == 0u)
    return false;
  qbs_plan_cursor_t cursor;
  qbs_plan_cursor_reset(&cursor);
  bool saw_command = false;
  for (;;) {
    qbs_command_t command;
    int has_command;
    if (qbs_plan_next(plan, &cursor, &command, &has_command) != QBS_STATUS_OK)
      return false;
    if (!has_command) return saw_command;
    saw_command = true;
    unsigned rows;
    if (command.activation_layout == QBS_ACTIVATION_LAYOUT_ROW_MAJOR && command.m == 1u)
      rows = 1u;
    else if (command.activation_layout == QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED && command.m == 4u)
      rows = 4u;
    else if (command.activation_layout == QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED &&
             command.m >= 5u && command.m <= 8u)
      rows = 8u;
    else return false;
    const size_t bytes = (size_t)rows * command.k_blocks *
        qbs_activation_block_bytes(plan->problem.activation_profile);
    if (command.gather_activation || command.accumulate || command.k_block_start != 0u ||
        command.k_blocks != plan->k_blocks || command.m > caps->activation_context_max_m ||
        command.k_blocks > caps->activation_context_max_k_blocks ||
        (caps->activation_context_layouts & (UINT16_C(1) << command.activation_layout)) == 0u ||
        (command.output_start == 0u && command.n == plan->problem.n) ||
        bytes > caps->activation_context_capacity_bytes)
      return false;
  }
}

static unsigned checked, eligible;
static int one(const qbs_device_t *device, unsigned wp, unsigned ap,
               unsigned storage, unsigned m, unsigned n, unsigned blocks,
               unsigned segment) {
  const unsigned elements = qbs_activation_block_elements(ap);
  const qbs_problem_t p = {(uint8_t)wp, (uint8_t)ap,
      QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR, (uint8_t)storage, m, n, blocks * elements};
  qbs_plan_t plan;
  const qbs_status_t status = segment
      ? qbs_plan_create_segmented_r4(device, &p, segment, &plan)
      : qbs_plan_create(device, &p, &plan);
  if (status != QBS_STATUS_OK) return 0;
  const bool expected = full_scan(&plan, &device->capabilities);
  if (!!qbs_plan_supports_activation_context(&plan) != expected) {
    fprintf(stderr, "Mismatch wp=%u ap=%u storage=%u m=%u n=%u blocks=%u segment=%u\n",
            wp, ap, storage, m, n, blocks, segment);
    return 1;
  }
  ++checked;
  eligible += expected;
  return 0;
}

int main(void) {
  const unsigned vlens[] = {128, 256, 512, 1024};
  const unsigned blocks[] = {1, 2, 3, 8, 15, 16, 17, 24, 31, 32, 33};
  for (unsigned v = 0; v < sizeof(vlens)/sizeof(vlens[0]); ++v) {
    qbs_device_t reference;
    CHECK(qbs_device_init_reference(vlens[v], &reference) == QBS_STATUS_OK);
    for (unsigned variant = 0; variant < 11; ++variant) {
      qbs_device_t device = reference;
      switch (variant) {
        case 1: device.capabilities.activation_context_max_m = 1; break;
        case 2: device.capabilities.activation_context_max_k_blocks = 8; break;
        case 3: device.capabilities.activation_context_capacity_bytes = 1024; break;
        case 4: device.capabilities.activation_context_layouts &=
                    ~(UINT16_C(1) << QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED); break;
        case 5: device.capabilities.activation_context_layouts &=
                    ~(UINT16_C(1) << QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED); break;
        case 6: device.capabilities.activation_context_access_modes = 0; break;
        case 7: device.capabilities.activation_context_profiles = 0; break;
        case 8: device.capabilities.activation_context_count = 0; break;
        case 9: device.capabilities.activation_context_generation_bits = 9; break;
        case 10: device.capabilities.activation_context_capacity_bytes = 0; break;
      }
      for (unsigned wp = 1; wp < 16; ++wp) for (unsigned ap = 1; ap < 16; ++ap) {
        if (!qbs_device_supports_profile(&device, wp, ap)) continue;
        for (unsigned storage = 0; storage < 3; ++storage)
        for (unsigned m = 1; m <= 25; ++m)
        for (unsigned n = 1; n <= 2u*device.capabilities.max_n + 3u; ++n)
        for (unsigned k = 0; k < sizeof(blocks)/sizeof(blocks[0]); ++k) {
          CHECK(one(&device, wp, ap, storage, m, n, blocks[k], 0) == 0);
        }
      }
    }
  }
  qbs_device_t device;
  CHECK(qbs_device_init_reference(1024, &device) == QBS_STATUS_OK);
  for (unsigned m = 1; m <= 17; ++m) for (unsigned storage = 0; storage < 3; ++storage) {
    CHECK(one(&device, QBS_WEIGHT_PROFILE_Q4_K, QBS_ACTIVATION_PROFILE_Q8_K,
              storage, m, 151936, 8, 0) == 0);
    CHECK(one(&device, QBS_WEIGHT_PROFILE_Q4_0, QBS_ACTIVATION_PROFILE_Q8_0,
              storage, m, 151937, 16, 16) == 0);
  }
  CHECK(eligible > 0);
  printf("QBS_CONTEXT_ADMISSION_PASS plans=%u eligible=%u\n", checked, eligible);
  return 0;
}
