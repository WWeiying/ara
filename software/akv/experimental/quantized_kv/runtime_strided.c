#include "runtime_strided.h"
#include "native.h"
#include "selection_strided.h"

typedef struct __attribute__((aligned(64))) {
  akv_quant_native_workspace_t core;
  unsigned char key_panel[AKV_QUANT_TILE * (AKV_QUANT_MAX_DIM / 32u) * 34u]
      __attribute__((aligned(64)));
  unsigned panel_valid, panel_head, panel_first, panel_tokens;
} akv_quant_strided_workspace_t;

typedef struct {
  akv_quant_native_context_t core;
  akv_quant_strided_workspace_t *workspace;
  akv_quant_strided_report_t *report;
} akv_quant_strided_context_t;

static int strided_value(void *opaque, unsigned token, float *value, unsigned dim) {
  akv_quant_strided_context_t *c = opaque;
  return akv_quant_native_value(&c->core, token, value, dim);
}

static int strided_qk(void *opaque, unsigned first_head, unsigned heads,
    unsigned first_token, unsigned tokens, float *scores, size_t stride) {
  akv_quant_strided_context_t *c = opaque;
  const akv_quant_selection_input_t *input = c->core.input;
  const akv_quant_selection_t *selection = c->core.selection;
  akv_quant_strided_workspace_t *w = c->workspace;
  if (input->key.token_stride == selection->key_row_bytes)
    return akv_quant_native_qk(&c->core, first_head, heads, first_token, tokens, scores, stride);
  if (!heads || first_head > selection->group_heads ||
      heads > selection->group_heads - first_head || !tokens || tokens > AKV_QUANT_TILE ||
      first_token >= selection->visible_tokens ||
      tokens > selection->visible_tokens - first_token || stride < tokens)
    return 1;
  /* One bounded panel per KV head/tile, reused by every M4/M2/M1 group.
   * Do not read masked tail rows or copy/requantize the whole cache. */
  if (!w->panel_valid || w->panel_head != c->core.kv_head ||
      w->panel_first != first_token || w->panel_tokens != tokens) {
    const unsigned char *source = (const unsigned char *)input->key.data +
        c->core.kv_head * input->key.head_stride + first_token * input->key.token_stride;
    for (unsigned token = 0; token < tokens; ++token)
      memcpy(w->key_panel + token * selection->key_row_bytes,
          source + token * input->key.token_stride, selection->key_row_bytes);
    w->panel_valid = 1;
    w->panel_head = c->core.kv_head;
    w->panel_first = first_token;
    w->panel_tokens = tokens;
    ++c->report->key_panels;
    c->report->key_bytes += tokens * selection->key_row_bytes;
  }
  /* Reuse the original descriptor/executor path on a local contiguous view.
   * Both the request coordinates and selected extent are now panel-relative. */
  akv_quant_selection_input_t packed = *input;
  packed.key.data = w->key_panel;
  packed.key.token_stride = selection->key_row_bytes;
  packed.key.head_stride = sizeof(w->key_panel);
  akv_quant_selection_t panel_selection = *selection;
  panel_selection.visible_tokens = tokens;
  akv_quant_native_context_t panel = c->core;
  panel.input = &packed;
  panel.selection = &panel_selection;
  panel.kv_head = 0;
  return akv_quant_native_qk(&panel, first_head, heads, 0, tokens, scores, stride);
}

size_t akv_quant_strided_workspace_bytes(void) {
  return sizeof(akv_quant_strided_workspace_t);
}

int akv_quant_strided_execute(const akv_quant_selection_input_t *input,
    const akv_quant_native_bindings_t *bindings, void *workspace,
    size_t workspace_bytes, akv_quant_strided_report_t *report) {
  if (!report) return AKV_QUANT_NATIVE_FALLBACK;
  memset(report, 0, sizeof(*report));
  if (!bindings || !bindings->quantize || !bindings->decode || !bindings->scale ||
      !bindings->mad || !bindings->execute) {
    report->native.selection_reason = AKV_QUANT_SELECT_FEATURE;
    return AKV_QUANT_NATIVE_FALLBACK;
  }
  if (!workspace || ((uintptr_t)workspace & 63u) ||
      workspace_bytes < sizeof(akv_quant_strided_workspace_t) ||
      sizeof(akv_quant_strided_workspace_t) > UINTPTR_MAX - (uintptr_t)workspace) {
    report->native.selection_reason = AKV_QUANT_SELECT_LAYOUT;
    return AKV_QUANT_NATIVE_FALLBACK;
  }
  akv_quant_selection_t selection;
  report->native.selection_reason = akv_quant_select_strided(input, &selection);
  if (report->native.selection_reason != AKV_QUANT_SELECT_OK)
    return AKV_QUANT_NATIVE_FALLBACK;
  const akv_quant_tensor_view_t *views[] = {&input->query, &input->key, &input->value, &input->output};
  for (unsigned i = 0; i < 4; ++i)
    if (akv_quant_overlap(workspace, sizeof(akv_quant_strided_workspace_t),
                         views[i]->data, views[i]->bytes)) {
      report->native.selection_reason = AKV_QUANT_SELECT_ALIAS;
      return AKV_QUANT_NATIVE_FALLBACK;
    }
  if (akv_quant_overlap(workspace, sizeof(akv_quant_strided_workspace_t), input->mask, input->mask_bytes)) {
    report->native.selection_reason = AKV_QUANT_SELECT_ALIAS;
    return AKV_QUANT_NATIVE_FALLBACK;
  }
  akv_quant_strided_workspace_t *w = workspace;
  w->panel_valid = 0;
  akv_quant_strided_context_t context = {
      {input, bindings, &selection, &w->core, &report->native, 0}, w, report};
  const akv_quant_online_plan_t plan = {selection.group_heads, selection.dim,
      selection.visible_tokens, input->scale, &context, strided_qk,
      strided_value, bindings->scale, bindings->mad};
  for (unsigned kv_head = 0; kv_head < selection.kv_heads; ++kv_head) {
    context.core.kv_head = kv_head;
    const unsigned first_head = kv_head * selection.group_heads;
    for (unsigned head = 0; head < selection.group_heads; ++head)
      bindings->quantize((const float *)((const unsigned char *)input->query.data +
          (first_head + head) * input->query.head_stride),
          w->core.query + head * selection.query_quant_row_bytes, selection.dim);
    float *output = (float *)((unsigned char *)input->output.data + first_head * input->output.head_stride);
    if (akv_quant_online_shared(&plan, output, input->output.head_stride / sizeof(float),
                                &w->core.online) != AKV_QUANT_OK)
      return AKV_QUANT_NATIVE_EXECUTION_FAILED;
    ++report->native.completed_groups;
  }
  return AKV_QUANT_NATIVE_OK;
}
