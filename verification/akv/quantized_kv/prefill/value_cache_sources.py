"""Derive an isolated V-cache executor from the current canonical executor."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT / 'software/akv/experimental/quantized_kv/prefill/execute.h'


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Canonical executor anchor changed: ' + before)
    return text.replace(before, after)


def generate(out):
    raw = SOURCE.read_text()
    start = raw.index('typedef struct __attribute__((aligned(64)))')
    end = raw.index('typedef struct {', start + 1)
    workspace = raw[start:end].replace('quant_prefill_workspace_t', 'vcache_workspace_t')
    workspace = replace_once(workspace, '  float output[', '  prefill_value_cache_t cache;\n  float output[')
    body = raw[raw.index('static inline int quant_prefill_execute('):raw.rindex('#endif')]
    body = body.replace('quant_prefill_execute(', 'vcache_execute(')
    body = body.replace('quant_prefill_workspace_t', 'vcache_workspace_t')
    body = replace_once(body, 'quant_prefill_report_t *report) {',
        'quant_prefill_report_t *report,\n'
        '    void (*pure_decoder)(const void *, float *, int64_t)) {')
    body = replace_once(body, '  if(!bindings || !bindings->quantize',
        '  if(!pure_decoder || !bindings || bindings->decode != pure_decoder || !bindings->quantize')
    body = replace_once(body, '      unsigned rows=total-first;',
        '      if (!first) prefill_value_cache_reset(&w->cache, dim);\n'
        '      unsigned rows=total-first;')
    body = replace_once(body,
        '&w->panel,quant_prefill_panel_qk,quant_prefill_panel_value,bindings->scale,bindings->mad',
        'w,vcache_qk,vcache_value,bindings->scale,bindings->mad')
    helpers = r'''
/* The extra decoder argument is a caller attestation of purity, NOT a way
 * to infer purity from arbitrary function pointers. Only reviewed adapters
 * may provide it. The production generic entry remains unchanged. */
static inline int vcache_qk(void *opaque, unsigned first, unsigned rows,
    unsigned token, unsigned tokens, float *out, size_t stride) {
  vcache_workspace_t *w = opaque;
  return quant_prefill_panel_qk(&w->panel, first, rows, token, tokens, out, stride);
}
static inline int vcache_value(void *opaque, unsigned token, float *out, unsigned dim) {
  vcache_workspace_t *w = opaque;
  const akv_quant_selection_t *s = w->panel.native.core.selection;
  if (token >= s->visible_tokens || dim != s->dim) return 1;
  return prefill_value_cache_get(&w->cache, quant_prefill_panel_value,
      &w->panel, token, out, dim);
}
'''
    (out / 'value_cache_execute.h').write_text(
        '#include "software/akv/experimental/quantized_kv/prefill/execute.h"\n'
        '#include "value_cache_candidate.h"\n' + workspace + helpers + body)
    return [SOURCE, HERE / 'value_cache_candidate.h', Path(__file__)]
