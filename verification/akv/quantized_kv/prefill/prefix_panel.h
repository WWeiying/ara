#ifndef QUANT_PREFILL_PREFIX_PANEL_H
#define QUANT_PREFILL_PREFIX_PANEL_H

#include "native_prefix.h"

/* Private, synchronous, pre-admitted one-KV-head context. Initialize once per
 * row group. Inputs remain immutable until that group's execution completes. */
typedef struct {
  quant_prefill_native_context_t native;
  unsigned valid, first, count, head, panels;
  size_t copied_bytes;
  unsigned char key[AKV_QUANT_TILE * (AKV_QUANT_MAX_DIM / 32u) * 34u]
      __attribute__((aligned(64)));
} quant_prefill_panel_context_t;

static inline int quant_prefill_panel_qk(void *opaque, unsigned first,
    unsigned rows, unsigned token, unsigned tokens, float *out, size_t stride) {
  quant_prefill_panel_context_t *c = opaque;
  quant_prefill_native_context_t *native = &c->native;
  const akv_quant_selection_t *s = native->core.selection;
  const akv_quant_selection_input_t *input = native->core.input;
  if (input->key.token_stride == s->key_row_bytes)
    return quant_prefill_native_qk(native, first, rows, token, tokens, out, stride);
  if (!native->visible || s->group_heads>AKV_QUANT_MAX_HEADS || !rows || rows > 4 || first > s->group_heads ||
      rows > s->group_heads-first || !tokens || tokens > AKV_QUANT_TILE ||
      stride < tokens || token % AKV_QUANT_TILE || !s->key_row_bytes ||
      s->key_row_bytes > sizeof(c->key)/AKV_QUANT_TILE ||
      input->key.token_stride < s->key_row_bytes) return 1;
  unsigned maximum = 0;
  for (unsigned row=0; row<s->group_heads; ++row) {
    if (!native->visible[row] || native->visible[row]>s->visible_tokens) return 1;
    if (native->visible[row]>maximum) maximum=native->visible[row];
  }
  for (unsigned row=first; row<first+rows; ++row)
    if (token>=native->visible[row] || tokens>native->visible[row]-token) return 1;
  if (token>=maximum) return 1;
  unsigned count=maximum-token;
  if (count>AKV_QUANT_TILE) count=AKV_QUANT_TILE;
  if (tokens>count) return 1;
  if (!c->valid || c->head!=native->core.kv_head || c->first!=token || c->count!=count) {
    const unsigned char *source=(const unsigned char *)input->key.data +
      native->core.kv_head*input->key.head_stride + token*input->key.token_stride;
    for (unsigned i=0;i<count;++i)
      memcpy(c->key+i*s->key_row_bytes,source+i*input->key.token_stride,s->key_row_bytes);
    c->valid=1; c->head=native->core.kv_head; c->first=token; c->count=count;
    ++c->panels; c->copied_bytes+=count*s->key_row_bytes;
  }
  /* The panel covers the union of visible prefixes. Commands still use each
   * row group's shorter length; no masked score element is calculated. */
  akv_quant_selection_input_t packed=*input;
  packed.key.data=c->key; packed.key.token_stride=s->key_row_bytes;
  packed.key.head_stride=sizeof(c->key);
  akv_quant_selection_t local=*s; local.visible_tokens=count;
  unsigned remaining[AKV_QUANT_MAX_HEADS];
  for(unsigned row=0;row<s->group_heads;++row)
    remaining[row]=native->visible[row]>token ? native->visible[row]-token : 0;
  akv_quant_native_context_t saved=native->core;
  const unsigned *saved_visible=native->visible;
  native->core.input=&packed; native->core.selection=&local; native->core.kv_head=0;
  native->visible=remaining;
  int status=quant_prefill_native_qk(native,first,rows,0,tokens,out,stride);
  native->core=saved; native->visible=saved_visible;
  return status;
}

static inline int quant_prefill_panel_value(void *opaque, unsigned token,
    float *out, unsigned dim) {
  quant_prefill_panel_context_t *c=opaque;
  return quant_prefill_native_value(&c->native,token,out,dim);
}
#endif
