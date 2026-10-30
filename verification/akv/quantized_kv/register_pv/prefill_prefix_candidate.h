#ifndef QUANT_REGISTER_PREFILL_PREFIX_H
#define QUANT_REGISTER_PREFILL_PREFIX_H

#include "software/akv/experimental/quantized_kv/register_pv/online.h"

/* Experimental internal kernel: rows belong to one KV head; all buffers and
 * callbacks must already satisfy admission/ownership rules. Not a GGML API.
 * Each row has a positive visible prefix. Never issue QK for masked positions.
 * After output initialization, callback errors are terminal, not fallback. */
static inline int quant_register_prefill_prefix(const akv_quant_online_plan_t *p,
    const unsigned *visible, float *output, size_t stride,
    akv_quant_online_workspace_t *w, const quant_register_pv_view_t *view) {
  if (!visible || !akv_quant_online_valid(p, output, stride, w))
    return AKV_QUANT_BAD_ARGUMENT;
  unsigned maximum = 0;
  for (unsigned row = 0; row < p->heads; ++row) {
    if (!visible[row] || visible[row] > p->tokens) return AKV_QUANT_BAD_ARGUMENT;
    if (row && visible[row]<visible[row-1]) return AKV_QUANT_BAD_ARGUMENT;
    if (visible[row] > maximum) maximum = visible[row];
  }
  /* Internal schedule: caller owns disjoint, immutable validated input views. */
  const size_t row_bytes=p->dim/32*34;
  uintptr_t vlenb,frm,vstart;
  __asm__ volatile("csrr %0,vlenb;csrr %1,frm;csrr %2,vstart"
                   :"=r"(vlenb),"=r"(frm),"=r"(vstart)::"memory");
  if(vlenb!=128 || frm || vstart || !view || !view->data ||
     view->token_stride<row_bytes || view->bytes<row_bytes ||
     view->bytes>UINTPTR_MAX-(uintptr_t)view->data ||
     akv_grouped_pv_stride_exceeds(view->token_stride,maximum-1,view->bytes-row_bytes))
    return AKV_QUANT_BAD_ARGUMENT;
  akv_quant_online_init(p, output, stride, w);
  for (unsigned first = 0; first < maximum; first += AKV_QUANT_TILE) {
    unsigned lengths[AKV_QUANT_MAX_HEADS];
    unsigned tokens = maximum - first;
    if (tokens > AKV_QUANT_TILE) tokens = AKV_QUANT_TILE;
    for (unsigned row = 0; row < p->heads; ++row) {
      unsigned n = visible[row] > first ? visible[row] - first : 0;
      lengths[row] = n < tokens ? n : tokens;
    }
    for (unsigned row = 0; row < p->heads;) {
      if (!lengths[row]) { ++row; continue; }
      unsigned end = row + 1;
      while (end < p->heads && lengths[end] == lengths[row]) ++end;
      while (row < end) {
        const unsigned left = end - row;
        const unsigned group = left >= 4 ? 4 : left >= 2 ? 2 : 1;
        if (p->qk(p->context, row, group, first, lengths[row],
                  &w->score[row][0], AKV_QUANT_TILE)) return AKV_QUANT_QK_FAILED;
        row += group;
      }
    }
    for (unsigned token = 0; token < tokens; ++token) {
      unsigned active=0;
      while(active<p->heads && token>=lengths[active]) ++active;
      if(active==p->heads) return AKV_QUANT_BAD_ARGUMENT;
      float ms[AKV_QUANT_MAX_HEADS],vs[AKV_QUANT_MAX_HEADS];
      unsigned rescale=0;
      for(unsigned row=active;row<p->heads;++row) {
        float score=w->score[row][token]*p->score_scale;
        score+=0.0f;
        ms[row]=vs[row]=1.0f;
        const float old=w->maximum[row];
        if(score>old) {
          w->maximum[row]=score;
          ms[row]=expf(old-score);
          rescale|=1u<<row;
        } else vs[row]=expf(score-old);
      }
      const unsigned char *raw=view->data+(first+token)*view->token_stride;
      if(quant_register_pv_update(p->heads-active,p->dim,stride,output+active*stride,
                                 raw,ms+active,vs+active,rescale>>active)!=AKV_GROUPED_PV_OK)
        return AKV_QUANT_VALUE_FAILED;
      for(unsigned row=active;row<p->heads;++row)
        w->sum[row]=w->sum[row]*ms[row]+vs[row];
    }
  }
  akv_quant_online_finish(p, output, stride, w);
  return AKV_QUANT_OK;
}

#endif
