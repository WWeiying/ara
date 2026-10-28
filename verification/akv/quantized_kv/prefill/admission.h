#ifndef QUANT_PREFILL_ADMISSION_H
#define QUANT_PREFILL_ADMISSION_H

#include "software/akv/experimental/quantized_kv/selection_strided.h"

/* Experimental whole-operation admission, not an enabled GGML entry point.
 * Caller owns accessible byte extents, immutability, serialization, and a
 * disjoint result-plan buffer. No FP arithmetic or output writes occur here. */
enum { QUANT_PREFILL_MAX_QUERIES = 256 };
typedef struct {
  akv_quant_selection_input_t tensors;
  size_t mask_row_stride;
} quant_prefill_input_t;
typedef struct {
  akv_quant_selection_t common;
  unsigned queries;
  unsigned visible[QUANT_PREFILL_MAX_QUERIES];
} quant_prefill_admission_t;

static inline int quant_prefill_admit(const quant_prefill_input_t *request,
                                      quant_prefill_admission_t *result) {
  if (!request || !result) return AKV_QUANT_SELECT_DISABLED;
  const akv_quant_selection_input_t *p=&request->tensors;
  if(p->requested!=1) return AKV_QUANT_SELECT_DISABLED;
  unsigned queries=p->query.tokens;
  if (!queries || queries>QUANT_PREFILL_MAX_QUERIES || p->output.tokens!=queries ||
      !p->query.dim || p->query.dim>256 || p->query.dim%32 ||
      !p->key.tokens || p->key.tokens>65536)
    return AKV_QUANT_SELECT_SHAPE;
  const size_t row_bytes=p->query.dim*sizeof(float);
  if (!akv_quant_view_valid(&p->query,row_bytes,4) ||
      !akv_quant_view_valid(&p->output,row_bytes,4)) return AKV_QUANT_SELECT_LAYOUT;
  const akv_quant_tensor_view_t *views[]={&p->key,&p->value};
  for(unsigned i=0;i<2;++i) {
    if (!views[i]->data || !views[i]->bytes ||
        views[i]->bytes>UINTPTR_MAX-(uintptr_t)views[i]->data)
      return AKV_QUANT_SELECT_LAYOUT;
  }
  size_t mask_extent;
  if (!p->mask || (uintptr_t)p->mask%2 || request->mask_row_stride%2 ||
      request->mask_row_stride<p->key.tokens*sizeof(uint16_t) ||
      !akv_quant_mul_add(queries-1u,request->mask_row_stride,
                        p->key.tokens*sizeof(uint16_t),&mask_extent) ||
      mask_extent>p->mask_bytes || p->mask_bytes>UINTPTR_MAX-(uintptr_t)p->mask)
    return AKV_QUANT_SELECT_MASK;
  const akv_quant_tensor_view_t *inputs[]={&p->query,&p->key,&p->value};
  for(unsigned i=0;i<3;++i)
    if(akv_quant_overlap(p->output.data,p->output.bytes,inputs[i]->data,inputs[i]->bytes))
      return AKV_QUANT_SELECT_ALIAS;
  if(akv_quant_overlap(p->output.data,p->output.bytes,p->mask,p->mask_bytes))
    return AKV_QUANT_SELECT_ALIAS;
  quant_prefill_admission_t candidate;
  memset(&candidate,0,sizeof(candidate)); candidate.queries=queries;
  unsigned maximum=0,maximum_row=0;
  for(unsigned row=0;row<queries;++row) {
    unsigned hidden=0,visible=0;
    for(unsigned token=0;token<p->key.tokens;++token) {
      uint16_t bits;
      AKV_QUANT_FIELD_COPY(&bits,(const unsigned char *)p->mask+
          row*request->mask_row_stride+token*sizeof(bits),sizeof(bits));
      if(bits==0xfc00u) hidden=1;
      else if(bits==0 && !hidden) ++visible;
      else return AKV_QUANT_SELECT_MASK;
    }
    if(!visible) return AKV_QUANT_SELECT_MASK;
    candidate.visible[row]=visible;
    if(visible>maximum) { maximum=visible;maximum_row=row; }
  }
  /* One existing Decode selector checks capabilities, all KV scales in the
   * union of visible rows, and one Query row. Avoid rescanning KV per query. */
  akv_quant_selection_input_t slice=*p;
  size_t offset=maximum_row*p->query.token_stride;
  slice.query.data=(const unsigned char *)p->query.data+offset;
  slice.query.bytes-=offset; slice.query.tokens=1;
  offset=maximum_row*p->output.token_stride;
  slice.output.data=(const unsigned char *)p->output.data+offset;
  slice.output.bytes-=offset; slice.output.tokens=1;
  slice.mask=(const uint16_t *)((const unsigned char *)p->mask+maximum_row*request->mask_row_stride);
  slice.mask_bytes=p->key.tokens*sizeof(uint16_t);
  int reason=akv_quant_select_strided(&slice,&candidate.common);
  if(reason!=AKV_QUANT_SELECT_OK) return reason;
  unsigned grouped_rows=candidate.common.group_heads*queries;
  if(grouped_rows>8) grouped_rows=8;
  unsigned m=grouped_rows>=4 ? 4 : grouped_rows>=2 ? 2 : 1;
  unsigned n=maximum<32 ? maximum : 32;
  const qbs_capabilities_t *caps=&p->device->capabilities;
  if(caps->max_m<m || caps->max_results<m*n || caps->activation_alignment_log2>2)
    return AKV_QUANT_SELECT_CAPABILITY;
  /* Same bitwise source-domain checks as Decode, without changing FFLAGS. */
  for(unsigned row=0;row<queries;++row) if(row!=maximum_row)
    for(unsigned head=0;head<p->query.heads;++head)
      for(unsigned block=0;block<p->query.dim/32;++block) {
        uint32_t amax=0;
        for(unsigned d=0;d<32;++d) {
          uint32_t bits;
          AKV_QUANT_FIELD_COPY(&bits,(const unsigned char *)p->query.data+
              row*p->query.token_stride+head*p->query.head_stride+(block*32+d)*4,4);
          bits&=0x7fffffffu;
          if((bits&0x7f800000u)==0x7f800000u) return AKV_QUANT_SELECT_NONFINITE;
          if(bits>amax) amax=bits;
        }
        if(amax && (amax<0x03800000u || amax>0x4afde040u)) return AKV_QUANT_SELECT_QUERY_RANGE;
      }
  *result=candidate;
  return AKV_QUANT_SELECT_OK;
}
#endif
