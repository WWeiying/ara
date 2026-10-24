#ifndef AKV_QUANTIZED_KV_NATIVE_H
#define AKV_QUANTIZED_KV_NATIVE_H

#include "runtime.h"
#include "online.h"

/* Private C implementation. External C++ callers include runtime.h instead.
 * No reference or synthetic arithmetic is embedded in this shared kernel. */
typedef struct __attribute__((aligned(64))) {
  unsigned char query[AKV_QUANT_MAX_HEADS * (AKV_QUANT_MAX_DIM / 32u) * 34u];
  qbs_descriptor_t descriptor __attribute__((aligned(64)));
  akv_quant_online_workspace_t online;
} akv_quant_native_workspace_t;

typedef struct {
  const akv_quant_selection_input_t *input;
  const akv_quant_native_bindings_t *bindings;
  const akv_quant_selection_t *selection;
  akv_quant_native_workspace_t *workspace;
  akv_quant_native_report_t *report;
  unsigned kv_head;
} akv_quant_native_context_t;

static inline int akv_quant_native_qk(void *opaque, unsigned first_head, unsigned heads,
    unsigned first_token, unsigned tokens, float *scores, size_t stride) {
  akv_quant_native_context_t *c = (akv_quant_native_context_t *)opaque;
  if (!heads || first_head > c->selection->group_heads ||
      heads > c->selection->group_heads - first_head || !tokens || tokens > 32 ||
      first_token >= c->selection->visible_tokens ||
      tokens > c->selection->visible_tokens - first_token || stride < tokens)
    return 1;
  qbs_descriptor_fields_t fields;
  memset(&fields, 0, sizeof(fields));
  fields.descriptor_version = QBS_DESCRIPTOR_VERSION;
  fields.weight_profile = c->selection->key_profile;
  fields.activation_profile = QBS_ACTIVATION_PROFILE_Q8_0;
  fields.weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR;
  fields.activation_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR;
  fields.activation_access = QBS_ACTIVATION_ACCESS_DIRECT;
  fields.n = tokens;
  fields.k_blocks = c->selection->dim / 32u;
  c->workspace->descriptor.header = qbs_pack_descriptor_header(&fields);
  c->workspace->descriptor.weight_base = (uintptr_t)c->input->key.data +
      c->kv_head * c->input->key.head_stride + first_token * c->input->key.token_stride;
  ++c->report->command_attempts;
  c->report->executor_status = c->bindings->execute(c->bindings->executor_context,
      &c->workspace->descriptor, heads,
      c->workspace->query + first_head * c->selection->query_quant_row_bytes,
      scores, stride, tokens, 0);
  return c->report->executor_status != QBS_STATUS_OK;
}

static inline int akv_quant_native_value(void *opaque, unsigned token, float *value, unsigned dim) {
  akv_quant_native_context_t *c = (akv_quant_native_context_t *)opaque;
  if (token >= c->selection->visible_tokens || dim != c->selection->dim) return 1;
  const unsigned char *source = (const unsigned char *)c->input->value.data +
      c->kv_head * c->input->value.head_stride + token * c->input->value.token_stride;
  c->bindings->decode(source, value, dim);
  ++c->report->value_decodes;
  return 0;
}

/* FALLBACK is returned only before quantization, command issue or output
 * writes. After execution begins an error is not an invitation to retry the
 * ordinary path: output may be partial. Caller owns aligned disjoint workspace,
 * report storage, whole-call serialization and input lifetime. */
static inline int akv_quant_native_run(const akv_quant_selection_input_t *input,
    const akv_quant_native_bindings_t *bindings, akv_quant_native_workspace_t *workspace,
    akv_quant_native_report_t *report) {
  if (!report) return AKV_QUANT_NATIVE_FALLBACK;
  memset(report, 0, sizeof(*report));
  if (!bindings || !bindings->quantize || !bindings->decode || !bindings->scale ||
      !bindings->mad || !bindings->execute || !workspace || ((uintptr_t)workspace & 63u)) {
    report->selection_reason = AKV_QUANT_SELECT_FEATURE;
    return AKV_QUANT_NATIVE_FALLBACK;
  }
  akv_quant_selection_t selection;
  report->selection_reason = akv_quant_select(input, &selection);
  if (report->selection_reason != AKV_QUANT_SELECT_OK) return AKV_QUANT_NATIVE_FALLBACK;
  const uintptr_t address = (uintptr_t)workspace;
  if (sizeof(*workspace) > UINTPTR_MAX - address) {
    report->selection_reason = AKV_QUANT_SELECT_LAYOUT;
    return AKV_QUANT_NATIVE_FALLBACK;
  }
  const akv_quant_tensor_view_t *views[] = {&input->query, &input->key, &input->value, &input->output};
  for (unsigned i = 0; i < 4; ++i)
    if (akv_quant_overlap(workspace, sizeof(*workspace), views[i]->data, views[i]->bytes)) {
      report->selection_reason = AKV_QUANT_SELECT_ALIAS;
      return AKV_QUANT_NATIVE_FALLBACK;
    }
  if (akv_quant_overlap(workspace, sizeof(*workspace), input->mask, input->mask_bytes)) {
    report->selection_reason = AKV_QUANT_SELECT_ALIAS;
    return AKV_QUANT_NATIVE_FALLBACK;
  }
  akv_quant_native_context_t context = {input, bindings, &selection, workspace, report, 0};
  const akv_quant_online_plan_t plan = {selection.group_heads, selection.dim,
      selection.visible_tokens, input->scale, &context, akv_quant_native_qk,
      akv_quant_native_value, bindings->scale, bindings->mad};
  for (unsigned kv_head = 0; kv_head < selection.kv_heads; ++kv_head) {
    context.kv_head = kv_head;
    const unsigned first_head = kv_head * selection.group_heads;
    for (unsigned head = 0; head < selection.group_heads; ++head)
      bindings->quantize((const float *)((const unsigned char *)input->query.data +
          (first_head + head) * input->query.head_stride),
          workspace->query + head * selection.query_quant_row_bytes, selection.dim);
    float *output = (float *)((unsigned char *)input->output.data + first_head * input->output.head_stride);
    if (akv_quant_online_shared(&plan, output, input->output.head_stride / sizeof(float),
                                &workspace->online) != AKV_QUANT_OK)
      return AKV_QUANT_NATIVE_EXECUTION_FAILED;
    ++report->completed_groups;
  }
  return AKV_QUANT_NATIVE_OK;
}

#endif
