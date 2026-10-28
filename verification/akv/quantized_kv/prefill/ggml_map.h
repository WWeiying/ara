#ifndef QUANT_PREFILL_GGML_MAP_H
#define QUANT_PREFILL_GGML_MAP_H

#include "software/akv/experimental/quantized_kv/ggml_decode.h"
#include "admission.h"

/* Metadata only. Accessible extents must still be verified by the backend,
 * followed by whole-call admission. Does not enable a production fast path. */
static inline int quant_prefill_ggml_map(const struct ggml_tensor *dst,
    const akv_quant_ggml_context_t *context, quant_prefill_input_t *result) {
  if (!context || context->requested != 1 || context->use_ref || !result)
    return AKV_QUANT_GGML_MAP_DISABLED;
  if (context->nth != 1 || context->ith != 0)
    return AKV_QUANT_GGML_MAP_THREADING;
  if (!dst || dst->op != GGML_OP_FLASH_ATTN_EXT)
    return AKV_QUANT_GGML_MAP_OPERATION;
  const struct ggml_tensor *q = dst->src[0], *mask = dst->src[3];
  if (!q || !mask) return AKV_QUANT_GGML_MAP_TYPE;
  if (!akv_quant_ggml_dims_valid(q) || !akv_quant_ggml_dims_valid(mask) ||
      !akv_quant_ggml_dims_valid(dst) || q->ne[1] > QUANT_PREFILL_MAX_QUERIES ||
      dst->ne[2] != q->ne[1] || mask->ne[1] < q->ne[1])
    return AKV_QUANT_GGML_MAP_SHAPE;

  /* Reuse the Decode mapper's operation/type/feature metadata checks on local
   * single-query views, then restore the original token dimensions/strides.
   * No tensor data or caller-owned metadata is modified or dereferenced. */
  struct ggml_tensor one_q = *q, one_mask = *mask, one_dst = *dst;
  one_q.ne[1] = 1;
  one_mask.ne[1] = 1;
  one_dst.ne[2] = 1;
  one_dst.src[0] = &one_q;
  one_dst.src[3] = &one_mask;
  quant_prefill_input_t mapped;
  memset(&mapped, 0, sizeof(mapped));
  int reason = akv_quant_ggml_map(&one_dst, context, &mapped.tensors);
  if (reason != AKV_QUANT_GGML_MAP_OK) return reason;
  mapped.tensors.query.tokens = (unsigned)q->ne[1];
  mapped.tensors.output.tokens = (unsigned)dst->ne[2];
  mapped.mask_row_stride = mask->nb[1];
  *result = mapped;
  return AKV_QUANT_GGML_MAP_OK;
}
#endif
