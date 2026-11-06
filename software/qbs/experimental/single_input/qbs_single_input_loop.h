#ifndef QBS_SINGLE_INPUT_LOOP_H_
#define QBS_SINGLE_INPUT_LOOP_H_

/* Private candidate: included after the generic planner. All public argument
   and context validation remains in qbs_execute_with_options before entry. */
static bool qbs_single_input_eligible(const qbs_plan_t *plan) {
  return plan->problem.m == 1u && !plan->split_k &&
      !plan->needs_activation_gather && plan->command_m != 0u &&
      plan->k_blocks != 0u && plan->k_blocks <= QBS_MAX_K_BLOCKS &&
      plan->command_k_blocks >= plan->k_blocks &&
      plan->command_n != 0u && plan->command_n <= QBS_MAX_N &&
      plan->weight_segment_k_blocks == 0u &&
      plan->weight_storage_rows == 0u && plan->weight_row_start == 0u &&
      (plan->problem.weight_layout == QBS_WEIGHT_LAYOUT_ROW_MAJOR ||
       (plan->problem.weight_layout == QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR &&
        (plan->command_n & 3u) == 0u)) &&
      (plan->problem.activation_storage == QBS_ACTIVATION_STORAGE_ROW_MAJOR ||
       plan->problem.activation_storage == QBS_ACTIVATION_STORAGE_M4_GROUPED);
}

static uint8_t qbs_single_input_access(bool use_context, uint8_t scope,
                                       bool first, bool last) {
  if (!use_context) return QBS_ACTIVATION_ACCESS_DIRECT;
  switch (scope) {
    case QBS_ACTIVATION_CONTEXT_SCOPE_OPERATION:
      return first ? QBS_ACTIVATION_ACCESS_FILL
          : last ? QBS_ACTIVATION_ACCESS_RELEASE : QBS_ACTIVATION_ACCESS_REUSE;
    case QBS_ACTIVATION_CONTEXT_SCOPE_FILL_KEEP:
      return first ? QBS_ACTIVATION_ACCESS_FILL : QBS_ACTIVATION_ACCESS_REUSE;
    case QBS_ACTIVATION_CONTEXT_SCOPE_REUSE_KEEP:
      return QBS_ACTIVATION_ACCESS_REUSE;
    case QBS_ACTIVATION_CONTEXT_SCOPE_REUSE_RELEASE:
      return last ? QBS_ACTIVATION_ACCESS_RELEASE : QBS_ACTIVATION_ACCESS_REUSE;
    default:
      return QBS_ACTIVATION_ACCESS_DIRECT; /* Rejected by the public entry. */
  }
}

/* Keep the one-row loop out of the large generic frame even under flatten. */
#if defined(__GNUC__) || defined(__clang__)
__attribute__((noinline))
#endif
static qbs_status_t qbs_execute_single_input(
    const qbs_plan_t *plan, const void *weights, const void *activations,
    float *output, size_t output_stride_elements, bool use_context,
    uint8_t scope, const qbs_execution_options_t *options,
    qbs_command_executor_t executor, void *executor_context) {
  const unsigned limit = plan->command_n;
  const unsigned total = plan->problem.n;
  const unsigned first_n = total < limit ? total : limit;
  const unsigned tail = (total - 1u) % limit + 1u;
  const size_t row_bytes = (size_t)plan->k_blocks *
      qbs_weight_block_bytes(plan->problem.weight_profile);
  qbs_descriptor_fields_t fields = {
      .descriptor_version = QBS_DESCRIPTOR_VERSION,
      .weight_profile = plan->problem.weight_profile,
      .activation_profile = plan->problem.activation_profile,
      .weight_layout = plan->problem.weight_layout,
      .activation_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR,
      .n = (uint8_t)first_n,
      .k_blocks = plan->k_blocks,
      .activation_access = qbs_single_input_access(use_context, scope, true,
                                                   total <= limit),
      .context_id = use_context ? options->activation_context.context_id : 0u,
      .context_generation = use_context
          ? options->activation_context.generation : 0u,
  };
  const uint64_t first_header = qbs_pack_descriptor_header(&fields);
  fields.n = (uint8_t)limit;
  fields.activation_access = qbs_single_input_access(use_context, scope,
                                                    false, false);
  const uint64_t middle_header = qbs_pack_descriptor_header(&fields);
  fields.n = (uint8_t)tail;
  fields.activation_access = qbs_single_input_access(use_context, scope,
                                                    false, true);
  const uint64_t last_header = qbs_pack_descriptor_header(&fields);
  const uint8_t *weight_cursor = weights;
  float *output_cursor = output;
  unsigned remaining = total;
  bool first = true;
  for (;;) {
    const unsigned n = remaining < limit ? remaining : limit;
    const qbs_descriptor_t descriptor = {
        .header = first ? first_header
            : remaining <= limit ? last_header : middle_header,
        .weight_base = (uintptr_t)weight_cursor,
    };
    const qbs_status_t status = executor(executor_context, &descriptor, 1u,
        activations, output_cursor, output_stride_elements, n, 0);
    if (status != QBS_STATUS_OK || remaining == n) return status;
    remaining -= n;
    weight_cursor += (size_t)n * row_bytes;
    output_cursor += n;
    first = false;
  }
}

#endif
