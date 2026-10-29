#ifndef QUANT_REGISTER_PV_ONLINE_CANDIDATE_H
#define QUANT_REGISTER_PV_ONLINE_CANDIDATE_H

#include "kernel.h"
#include "software/akv/experimental/quantized_kv/online.h"

/* Experimental explicit Q8_0 view: no pretend value callback that returns
 * success without filling its destination. Stride and extent are bytes for
 * one KV head, already selected by the enclosing runtime. All input contents
 * and callback bindings must remain immutable during this call. Admission
 * establishes finite Q/K/V, zero-mask prefix and production arithmetic.
 * Only pre-entry rejection permits fallback; callback errors are terminal.
 * The existing value/MAD callbacks are intentionally bypassed by this opt-in. */
typedef struct {
  const unsigned char *data;
  size_t token_stride;
  size_t bytes;
} quant_register_pv_view_t;

static inline int quant_register_online(const akv_quant_online_plan_t *p,
    float *output, size_t stride, akv_quant_online_workspace_t *w,
    const quant_register_pv_view_t *view) {
  if (!akv_grouped_pv_span(p, sizeof(*p)) ||
      (uintptr_t)p % __alignof__(*p) ||
      !akv_grouped_pv_span(w, sizeof(*w)) ||
      (uintptr_t)w % __alignof__(*w) ||
      !view || (uintptr_t)view % __alignof__(*view) ||
      sizeof(*view) > UINTPTR_MAX-(uintptr_t)view ||
      !akv_quant_online_valid(p, output, stride, w))
    return AKV_QUANT_BAD_ARGUMENT;
  const size_t row = p->dim / 32 * 34;
  if (!view->data || view->token_stride < row ||
      view->bytes > UINTPTR_MAX-(uintptr_t)view->data ||
      view->bytes < row ||
      akv_grouped_pv_stride_exceeds(view->token_stride, p->tokens-1,
                                   view->bytes-row))
    return AKV_QUANT_BAD_ARGUMENT;
  const size_t out_bytes=((p->heads-1)*stride+p->dim)*sizeof(float);
  if (!akv_grouped_pv_span(output, out_bytes) ||
      akv_grouped_pv_overlap(output,out_bytes,w,sizeof(*w)) ||
      akv_grouped_pv_overlap(output,out_bytes,p,sizeof(*p)) ||
      akv_grouped_pv_overlap(output,out_bytes,view,sizeof(*view)) ||
      akv_grouped_pv_overlap(output,out_bytes,view->data,view->bytes) ||
      akv_grouped_pv_overlap(w,sizeof(*w),p,sizeof(*p)) ||
      akv_grouped_pv_overlap(w,sizeof(*w),view,sizeof(*view)) ||
      akv_grouped_pv_overlap(w,sizeof(*w),view->data,view->bytes))
    return AKV_QUANT_BAD_ARGUMENT;
  uintptr_t vlenb, frm;
  __asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
  __asm__ volatile("csrr %0,frm":"=r"(frm));
  if (vlenb!=128 || frm!=0) return AKV_QUANT_BAD_ARGUMENT;

  akv_quant_online_init(p,output,stride,w);
  for (unsigned first=0;first<p->tokens;first+=AKV_QUANT_TILE) {
    const unsigned remaining=p->tokens-first;
    const unsigned tokens=remaining<AKV_QUANT_TILE ? remaining : AKV_QUANT_TILE;
    for (unsigned head=0;head<p->heads;) {
      const unsigned left=p->heads-head;
      const unsigned rows=left>=4 ? 4 : left>=2 ? 2 : 1;
      if (p->qk(p->context,head,rows,first,tokens,
                &w->score[head][0],AKV_QUANT_TILE))
        return AKV_QUANT_QK_FAILED;
      head+=rows;
    }
    for (unsigned token=0;token<tokens;++token) {
      float ms[AKV_QUANT_MAX_HEADS],vs[AKV_QUANT_MAX_HEADS];
      unsigned rescale=0;
      for (unsigned head=0;head<p->heads;++head) {
        float s=w->score[head][token]*p->score_scale;
        s+=0.0f;
        const float old=w->maximum[head];
        ms[head]=vs[head]=1.0f;
        if (s>w->maximum[head]) {
          w->maximum[head]=s;
          ms[head]=expf(old-s);
          rescale|=1u<<head;
        } else {
          vs[head]=expf(s-w->maximum[head]);
        }
      }
      const unsigned char *raw=view->data+(first+token)*view->token_stride;
      if (quant_register_pv_update(p->heads,p->dim,stride,output,raw,
                                  ms,vs,rescale)!=AKV_GROUPED_PV_OK)
        return AKV_QUANT_VALUE_FAILED;
      for (unsigned head=0;head<p->heads;++head)
        w->sum[head]=w->sum[head]*ms[head]+vs[head];
    }
  }
  akv_quant_online_finish(p,output,stride,w);
  return AKV_QUANT_OK;
}

#endif
