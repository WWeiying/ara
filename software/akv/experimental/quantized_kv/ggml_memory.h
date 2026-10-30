#ifndef AKV_QUANTIZED_KV_GGML_MEMORY_H
#define AKV_QUANTIZED_KV_GGML_MEMORY_H

#include "ggml_decode.h"
#include "ggml-backend.h"

/* Compute the tensor's bounding byte span, not the entire allocation remainder.
 * GGML owns valid tensor/view objects; this is not an untrusted-pointer parser.
 * Backend host accessibility is checked, but normal-memory/coherency semantics
 * remain an explicit platform assertion in the caller's context. */
static inline int akv_quant_ggml_host_extent(const struct ggml_tensor *tensor,size_t *bytes) {
  if (!tensor || !bytes || !tensor->data || !akv_quant_ggml_dims_valid(tensor)) return 0;
  size_t block_bytes,block_elements;
  switch (tensor->type) {
    case GGML_TYPE_F32: block_bytes=4; block_elements=1; break;
    case GGML_TYPE_F16: block_bytes=2; block_elements=1; break;
    case GGML_TYPE_Q4_0: block_bytes=18; block_elements=32; break;
    case GGML_TYPE_Q8_0: block_bytes=34; block_elements=32; break;
    default: return 0;
  }
  if ((size_t)tensor->ne[0]%block_elements || tensor->nb[0]!=block_bytes) return 0;
  size_t span;
  if (!akv_quant_mul_add((size_t)tensor->ne[0]/block_elements,block_bytes,0,&span)) return 0;
  for (unsigned i=1;i<4;++i)
    if (!akv_quant_mul_add((size_t)tensor->ne[i]-1,tensor->nb[i],span,&span)) return 0;
  const struct ggml_tensor *owner=tensor;
  unsigned depth=0;
  while (!owner->buffer && owner->view_src && depth<64) {
    owner=owner->view_src;
    ++depth;
  }
  if (!owner->buffer || !ggml_backend_buffer_is_host(owner->buffer)) return 0;
  const uintptr_t base=(uintptr_t)ggml_backend_buffer_get_base(owner->buffer);
  const uintptr_t data=(uintptr_t)tensor->data;
  const size_t allocation=ggml_backend_buffer_get_size(owner->buffer);
  if (!base || !span || allocation>UINTPTR_MAX-base || data<base ||
      data-base>allocation || span>allocation-(data-base)) return 0;
  *bytes=span;
  return 1;
}

static inline int akv_quant_ggml_memory_context(const struct ggml_tensor *dst,
    const akv_quant_ggml_context_t *context,akv_quant_ggml_context_t *result) {
  if (!dst || !context || !result) return 0;
  akv_quant_ggml_context_t checked=*context;
  if (!akv_quant_ggml_host_extent(dst->src[0],&checked.query_bytes) ||
      !akv_quant_ggml_host_extent(dst->src[1],&checked.key_bytes) ||
      !akv_quant_ggml_host_extent(dst->src[2],&checked.value_bytes) ||
      !akv_quant_ggml_host_extent(dst->src[3],&checked.mask_bytes) ||
      !akv_quant_ggml_host_extent(dst,&checked.output_bytes)) return 0;
  *result=checked;
  return 1;
}

#endif
