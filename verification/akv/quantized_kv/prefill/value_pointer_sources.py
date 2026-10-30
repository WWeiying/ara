"""Successor to the sealed copy experiment: consume cached rows directly."""
from pathlib import Path
from value_cache_sources import generate as generate_copy, replace_once, HERE, ROOT


def generate(out):
    inputs=generate_copy(out)
    source=ROOT/'software/akv/experimental/quantized_kv/prefill/prefix_schedule.h'
    raw=source.read_text()
    schedule=raw[raw.index('static inline int quant_prefill_prefix_schedule('):raw.rindex('#endif')]
    schedule=replace_once(schedule,'quant_prefill_prefix_schedule(', 'vptr_schedule(')
    schedule=replace_once(schedule,'akv_quant_online_workspace_t *w) {',
        'akv_quant_online_workspace_t *w,\n'
        '    int (*get_value)(void *, unsigned, float *, unsigned, const float **)) {')
    schedule=replace_once(schedule,'if (!visible ||', 'if (!get_value || !visible ||')
    schedule=replace_once(schedule,
        '      if (p->value(p->context, first + token, w->value, p->dim))\n'
        '        return AKV_QUANT_VALUE_FAILED;',
        '      const float *value = NULL;\n'
        '      if (get_value(p->context, first + token, w->value, p->dim, &value) || !value)\n'
        '        return AKV_QUANT_VALUE_FAILED;')
    schedule=replace_once(schedule,'w->score[row][token], w->value,','w->score[row][token], value,')
    getter=r'''
/* The selected row is valid until this token's PV consumers finish. Cache
 * rows survive later groups; scratch is overwritten at the next miss outside
 * the cache. Neither pointer escapes the synchronous token loop. */
static inline int vptr_value(void *opaque, unsigned token, float *scratch,
    unsigned dim, const float **selected) {
  vcache_workspace_t *w=opaque;
  const akv_quant_selection_t *s=w->panel.native.core.selection;
  *selected=NULL;
  if(token>=s->visible_tokens || dim!=s->dim || dim!=w->cache.dim) return 1;
  if(token>=PREFILL_VCACHE_TOKENS) {
    int status=quant_prefill_panel_value(&w->panel,token,scratch,dim);
    if(!status) *selected=scratch;
    return status;
  }
  const uint32_t bit=UINT32_C(1)<<token;
  if(!(w->cache.valid&bit)) {
    int status=quant_prefill_panel_value(&w->panel,token,w->cache.values[token],dim);
    if(status) return status;
    w->cache.valid|=bit;
  }
  *selected=w->cache.values[token];
  return 0;
}
'''
    dest=out/'value_cache_execute.h';body=dest.read_text()
    body=replace_once(body,'static inline int vcache_execute(',getter+'\n'+schedule+'\nstatic inline int vcache_execute(')
    body=replace_once(body,
        'quant_prefill_prefix_schedule(&plan,visible,w->output[0],AKV_QUANT_MAX_DIM,&w->core.online)',
        'vptr_schedule(&plan,visible,w->output[0],AKV_QUANT_MAX_DIM,&w->core.online,vptr_value)')
    dest.write_text(body)
    return inputs+[source,Path(__file__)]
