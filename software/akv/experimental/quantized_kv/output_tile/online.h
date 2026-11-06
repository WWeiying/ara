#ifndef AKV_QUANT_OUTPUT_TILE_ONLINE_H
#define AKV_QUANT_OUTPUT_TILE_ONLINE_H

#include "kernel.h"
#include "software/akv/experimental/quantized_kv/register_pv/online.h"

/* Opt-in schedule, not a runtime default. Same finite/visible-prefix and
 * immutable-callback contract as Register-PV. No intermediate output, fflags
 * or workspace observation is allowed. QK failures after entry are terminal.
 * Coefficients postpone PV, but preserve the token order of each recurrence. */
static inline int akv_output_tile_online(const akv_quant_online_plan_t *p,
    float *output, size_t stride, akv_quant_online_workspace_t *w,
    const quant_register_pv_view_t *view) {
#if defined(__FAST_MATH__)
  (void)p; (void)output; (void)stride; (void)w; (void)view;
  return AKV_QUANT_BAD_ARGUMENT;
#else
  if (!akv_grouped_pv_span(p, sizeof(*p)) ||
      (uintptr_t)p % __alignof__(*p) ||
      !akv_grouped_pv_span(w, sizeof(*w)) ||
      (uintptr_t)w % __alignof__(*w) ||
      !akv_grouped_pv_span(view, sizeof(*view)) ||
      (uintptr_t)view % __alignof__(*view) ||
      !akv_quant_online_valid(p, output, stride, w))
    return AKV_QUANT_BAD_ARGUMENT;
  const size_t row=p->dim/32*34;
  const size_t bytes=((p->heads-1)*stride+p->dim)*sizeof(float);
  if ((uintptr_t)output % __alignof__(float) ||
      view->token_stride < row || view->bytes < row ||
      !view->data || view->bytes > UINTPTR_MAX-(uintptr_t)view->data ||
      akv_grouped_pv_stride_exceeds(view->token_stride, p->tokens-1,
                                  view->bytes-row) ||
      !akv_grouped_pv_span(output, bytes) ||
      akv_grouped_pv_overlap(output,bytes,w,sizeof(*w)) ||
      akv_grouped_pv_overlap(output,bytes,p,sizeof(*p)) ||
      akv_grouped_pv_overlap(output,bytes,view,sizeof(*view)) ||
      akv_grouped_pv_overlap(output,bytes,view->data,view->bytes) ||
      akv_grouped_pv_overlap(w,sizeof(*w),p,sizeof(*p)) ||
      akv_grouped_pv_overlap(w,sizeof(*w),view,sizeof(*view)) ||
      akv_grouped_pv_overlap(w,sizeof(*w),view->data,view->bytes))
    return AKV_QUANT_BAD_ARGUMENT;
  uintptr_t vlenb, frm, start;
  __asm__ volatile("csrr %0,vlenb; csrr %1,frm; csrr %2,vstart"
                   : "=r"(vlenb), "=r"(frm), "=r"(start) :: "memory");
  if (vlenb!=128 || frm!=0 || start!=0) return AKV_QUANT_BAD_ARGUMENT;

  akv_output_tile_coefficients_t coefficients;
  akv_quant_online_init(p,output,stride,w);
  for (unsigned first=0; first<p->tokens; first+=AKV_QUANT_TILE) {
    const unsigned remaining=p->tokens-first;
    const unsigned tokens=remaining<AKV_QUANT_TILE ? remaining : AKV_QUANT_TILE;
    for (unsigned head=0; head<p->heads;) {
      const unsigned left=p->heads-head;
      const unsigned rows=left>=4 ? 4 : left>=2 ? 2 : 1;
      if (p->qk(p->context,head,rows,first,tokens,
                &w->score[head][0],AKV_QUANT_TILE))
        return AKV_QUANT_QK_FAILED;
      head+=rows;
    }
    for (unsigned token=0; token<tokens; ++token) {
      coefficients.rescale[token]=0;
      for (unsigned head=0; head<p->heads; ++head) {
        float s=w->score[head][token]*p->score_scale;
        s+=0.0f;
        const float old=w->maximum[head];
        float ms=1.0f,vs=1.0f;
        if (s>old) {
          w->maximum[head]=s;
          ms=expf(old-s);
          coefficients.rescale[token]|=1u<<head;
        } else {
          vs=expf(s-old);
        }
        coefficients.ms[head][token]=ms;
        coefficients.vs[head][token]=vs;
        w->sum[head]=w->sum[head]*ms+vs;
      }
    }
    const size_t offset=first*view->token_stride;
    if (akv_output_tile_update(p->heads,p->dim,stride,output,view->data+offset,
          view->token_stride,view->bytes-offset,tokens,&coefficients)!=AKV_GROUPED_PV_OK)
      return AKV_QUANT_VALUE_FAILED;
  }
  akv_quant_online_finish(p,output,stride,w);
  return AKV_QUANT_OK;
#endif
}

#endif
