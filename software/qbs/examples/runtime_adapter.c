#include "qbs/qbs.h"

#include <stdio.h>

/* These identifiers deliberately belong to a fictitious runtime. A real
   adapter maps its own tensor metadata here; QBS never sees runtime enums. */
typedef enum {
  EXAMPLE_FORMAT_S4_B32_EXACT,
  EXAMPLE_FORMAT_GROUPWISE_INT4_G64,
  EXAMPLE_FORMAT_F16,
} example_format_t;

typedef enum {
  EXAMPLE_BINDING_FALLBACK,
  EXAMPLE_BINDING_EXACT,
  EXAMPLE_BINDING_CONVERT_AT_LOAD,
} example_binding_mode_t;

typedef struct {
  example_binding_mode_t mode;
  uint64_t weight_encoding_id;
  uint64_t activation_encoding_id;
} example_binding_t;

static example_binding_t bind_format(example_format_t format) {
  switch (format) {
    case EXAMPLE_FORMAT_S4_B32_EXACT:
      return (example_binding_t) {
          EXAMPLE_BINDING_EXACT,
          QBS_WEIGHT_ENCODING_S4_B32_F16_SPLIT_NIBBLE_OFFSET8,
          QBS_ACTIVATION_ENCODING_S8_B32_F16_TWOS_COMPLEMENT,
      };
    case EXAMPLE_FORMAT_GROUPWISE_INT4_G64:
      /* Equal bit width is not byte- or math-compatible. A runtime may supply
         a validated load-time converter, but must not claim a direct map. */
      return (example_binding_t) {
          EXAMPLE_BINDING_CONVERT_AT_LOAD,
          QBS_WEIGHT_ENCODING_S4_B32_F16_SPLIT_NIBBLE_OFFSET8,
          QBS_ACTIVATION_ENCODING_S8_B32_F16_TWOS_COMPLEMENT,
      };
    case EXAMPLE_FORMAT_F16:
      return (example_binding_t) {EXAMPLE_BINDING_FALLBACK, 0, 0};
  }
  return (example_binding_t) {EXAMPLE_BINDING_FALLBACK, 0, 0};
}

int main(void) {
  const example_binding_t direct = bind_format(EXAMPLE_FORMAT_S4_B32_EXACT);
  const example_binding_t foreign =
      bind_format(EXAMPLE_FORMAT_GROUPWISE_INT4_G64);
  const example_binding_t fallback = bind_format(EXAMPLE_FORMAT_F16);
  if (direct.mode != EXAMPLE_BINDING_EXACT ||
      foreign.mode != EXAMPLE_BINDING_CONVERT_AT_LOAD ||
      fallback.mode != EXAMPLE_BINDING_FALLBACK)
    return 1;

  qbs_device_t device;
  if (qbs_device_init_reference(1024, &device) != QBS_STATUS_OK)
    return 1;
  qbs_profile_binding_t resolved;
  if (qbs_device_bind_encodings(&device, direct.weight_encoding_id,
                                direct.activation_encoding_id,
                                &resolved) != QBS_STATUS_OK)
    return 1;
  const qbs_problem_t problem = {
      .weight_profile = resolved.weight_profile,
      .activation_profile = resolved.activation_profile,
      .weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR,
      .activation_storage = QBS_ACTIVATION_STORAGE_ROW_MAJOR,
      .m = 1,
      .n = 35,
      .k_elements = 1536,
  };
  qbs_plan_t plan;
  const qbs_status_t status = qbs_plan_create(&device, &problem, &plan);
  if (status != QBS_STATUS_OK)
    return 1;

  printf("profile=%s activation=%s commands=N%u/K%u conversion=%s\n",
         qbs_weight_profile_name(problem.weight_profile),
         qbs_activation_profile_name(problem.activation_profile),
         plan.command_n, plan.command_k_blocks,
         foreign.mode == EXAMPLE_BINDING_CONVERT_AT_LOAD ? "required" :
                                                           "not-required");
  return 0;
}
