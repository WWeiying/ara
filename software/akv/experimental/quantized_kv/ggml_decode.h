#ifndef AKV_QUANTIZED_KV_GGML_DECODE_H
#define AKV_QUANTIZED_KV_GGML_DECODE_H

#include "ggml.h"
#include "runtime.h"

/* Metadata bridge only: MAP_OK does not admit execution. The shared runtime
 * still performs capability, data, mask, alias and workspace checks once.
 * Extents are caller-verified accessible bytes from each tensor's data pointer,
 * not allocation sizes guessed from shape or view_src. No backend is installed
 * or enabled by including this file. */
typedef struct {
  unsigned requested, ith, nth, use_ref;
  unsigned vlen_bits, vstart, frm, normal_memory;
  const qbs_device_t *device;
  size_t query_bytes, key_bytes, value_bytes, mask_bytes, output_bytes;
} akv_quant_ggml_context_t;

enum {
  AKV_QUANT_GGML_MAP_OK = 0,
  AKV_QUANT_GGML_MAP_DISABLED,
  AKV_QUANT_GGML_MAP_THREADING,
  AKV_QUANT_GGML_MAP_OPERATION,
  AKV_QUANT_GGML_MAP_TYPE,
  AKV_QUANT_GGML_MAP_SHAPE,
  AKV_QUANT_GGML_MAP_LAYOUT,
};

static inline int akv_quant_ggml_dims_valid(const struct ggml_tensor *tensor) {
  for (unsigned i=0; i<4; ++i)
    if (tensor->ne[i]<=0 || (uint64_t)tensor->ne[i]>UINT32_MAX) return 0;
  return 1;
}

static inline int akv_quant_ggml_map(const struct ggml_tensor *dst,
    const akv_quant_ggml_context_t *context, akv_quant_selection_input_t *input) {
  if (!context || context->requested!=1 || !input || context->use_ref)
    return AKV_QUANT_GGML_MAP_DISABLED;
  /* Until collective admission/failure handling exists, do not allow one CPU
   * worker to choose fallback while another has started writing the result. */
  if (context->nth!=1 || context->ith!=0) return AKV_QUANT_GGML_MAP_THREADING;
  if (!dst || dst->op!=GGML_OP_FLASH_ATTN_EXT ||
      (dst->op_params[3]!=GGML_PREC_DEFAULT && dst->op_params[3]!=GGML_PREC_F32))
    return AKV_QUANT_GGML_MAP_OPERATION;
  for (unsigned i=5; i<GGML_MAX_SRC; ++i)
    if (dst->src[i]) return AKV_QUANT_GGML_MAP_OPERATION;
  const struct ggml_tensor *q=dst->src[0], *k=dst->src[1], *v=dst->src[2], *mask=dst->src[3];
  if (!q || !k || !v || !mask || q->type!=GGML_TYPE_F32 ||
      (k->type!=GGML_TYPE_Q4_0 && k->type!=GGML_TYPE_Q8_0) ||
      v->type!=GGML_TYPE_Q8_0 || mask->type!=GGML_TYPE_F16 || dst->type!=GGML_TYPE_F32)
    return AKV_QUANT_GGML_MAP_TYPE;
  const struct ggml_tensor *all[]={q,k,v,mask,dst};
  for (unsigned i=0; i<5; ++i)
    if (!akv_quant_ggml_dims_valid(all[i])) return AKV_QUANT_GGML_MAP_SHAPE;
  if (q->ne[1]!=1 || q->ne[3]!=1 || k->ne[3]!=1 || v->ne[3]!=1 ||
      q->ne[0]!=k->ne[0] || q->ne[0]!=v->ne[0] || k->ne[1]!=v->ne[1] ||
      k->ne[2]!=v->ne[2] || dst->ne[0]!=q->ne[0] || dst->ne[1]!=q->ne[2] ||
      dst->ne[2]!=1 || dst->ne[3]!=1 || mask->ne[0]<k->ne[1] ||
      mask->ne[1]!=1 || mask->ne[2]!=1 || mask->ne[3]!=1)
    return AKV_QUANT_GGML_MAP_SHAPE;
  const size_t key_block=k->type==GGML_TYPE_Q4_0 ? 18u : 34u;
  if (q->nb[0]!=4 || k->nb[0]!=key_block || v->nb[0]!=34 ||
      mask->nb[0]!=2 || dst->nb[0]!=4)
    return AKV_QUANT_GGML_MAP_LAYOUT;
  akv_quant_selection_input_t mapped;
  memset(&mapped,0,sizeof(mapped));
  mapped.requested=context->requested;
  mapped.vlen_bits=context->vlen_bits;
  mapped.vstart=context->vstart;
  mapped.frm=context->frm;
  mapped.normal_memory=context->normal_memory;
  mapped.device=context->device;
  mapped.sinks_present=dst->src[4]!=NULL;
  mapped.key_encoding=k->type==GGML_TYPE_Q4_0 ? QBS_WEIGHT_ENCODING_Q4_0 : QBS_WEIGHT_ENCODING_Q8_0_WEIGHT;
  mapped.value_encoding=QBS_WEIGHT_ENCODING_Q8_0_WEIGHT;
  mapped.query.data=q->data; mapped.query.bytes=context->query_bytes;
  mapped.query.dim=(unsigned)q->ne[0]; mapped.query.tokens=1;
  mapped.query.heads=(unsigned)q->ne[2];
  mapped.query.token_stride=q->nb[1]; mapped.query.head_stride=q->nb[2];
  mapped.key.data=k->data; mapped.key.bytes=context->key_bytes;
  mapped.key.dim=(unsigned)k->ne[0]; mapped.key.tokens=(unsigned)k->ne[1];
  mapped.key.heads=(unsigned)k->ne[2];
  mapped.key.token_stride=k->nb[1]; mapped.key.head_stride=k->nb[2];
  mapped.value.data=v->data; mapped.value.bytes=context->value_bytes;
  mapped.value.dim=(unsigned)v->ne[0]; mapped.value.tokens=(unsigned)v->ne[1];
  mapped.value.heads=(unsigned)v->ne[2];
  mapped.value.token_stride=v->nb[1]; mapped.value.head_stride=v->nb[2];
  mapped.output.data=dst->data; mapped.output.bytes=context->output_bytes;
  mapped.output.dim=(unsigned)dst->ne[0]; mapped.output.tokens=1;
  mapped.output.heads=(unsigned)dst->ne[1];
  mapped.output.token_stride=dst->nb[2]; mapped.output.head_stride=dst->nb[1];
  mapped.mask=(const uint16_t *)mask->data; mapped.mask_bytes=context->mask_bytes;
  AKV_QUANT_FIELD_COPY(&mapped.scale,dst->op_params,sizeof(float));
  AKV_QUANT_FIELD_COPY(&mapped.max_bias,dst->op_params+1,sizeof(float));
  AKV_QUANT_FIELD_COPY(&mapped.softcap,dst->op_params+2,sizeof(float));
  *input=mapped;
  return AKV_QUANT_GGML_MAP_OK;
}

#endif
