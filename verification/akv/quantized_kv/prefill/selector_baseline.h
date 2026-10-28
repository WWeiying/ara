#ifndef QUANT_SELECTOR_FROZEN_BASELINE_H
#define QUANT_SELECTOR_FROZEN_BASELINE_H

#include "software/akv/experimental/quantized_kv/selection.h"

/* Temporary successor while selection.h is sealed. The selector body is an
 * exact copy except its name and the K token_stride equality becoming a lower
 * bound. Shared view validation still proves head/token non-overlap and bounds.
 * Admission does NOT make strided K directly executable by row-major QBS:
 * the caller must gather each bounded panel before issuing its descriptor.
 * Host tests pin the source hash and verify the complete body transformation. */
#define AKV_QUANT_SELECT_STRIDED_SOURCE_SHA256 \
  "d597ccdf8da49a14f029626825bdceb939af2029665216cd47a07c1acf00cff7"

static inline int akv_quant_select_strided_baseline(const akv_quant_selection_input_t *p,
                                   akv_quant_selection_t *selection) {
  if (!p || !selection || p->requested != 1u) return AKV_QUANT_SELECT_DISABLED;
  if (!p->device || p->vlen_bits != 1024 || p->vstart || p->frm || !p->normal_memory)
    return AKV_QUANT_SELECT_CAPABILITY;
  const uint32_t scale = akv_quant_float_bits(p->scale);
  /* The conservative scale ceiling also keeps scaled QK values finite for
   * the admitted D<=256, finite-F16-scale, signed-eight-bit operand domain. */
  if (!scale || (scale & UINT32_C(0x80000000)) || scale > UINT32_C(0x5f800000) ||
      (scale & UINT32_C(0x7f800000)) == UINT32_C(0x7f800000) ||
      (akv_quant_float_bits(p->max_bias) & UINT32_C(0x7fffffff)) ||
      (akv_quant_float_bits(p->softcap) & UINT32_C(0x7fffffff)) || p->sinks_present)
    return AKV_QUANT_SELECT_FEATURE;
  const unsigned dim = p->query.dim;
  if (!dim || dim > 256 || dim % 32 || p->query.tokens != 1 ||
      !p->query.heads || p->query.heads > 256 ||
      !p->key.tokens || p->key.tokens > 65536 ||
      !p->key.heads || p->key.heads > 256 ||
      p->key.heads > 262144u / p->key.tokens ||
      p->query.heads % p->key.heads || p->query.heads / p->key.heads > 8 ||
      p->key.dim != dim || p->value.dim != dim || p->output.dim != dim ||
      p->value.tokens != p->key.tokens || p->value.heads != p->key.heads ||
      p->output.tokens != 1 || p->output.heads != p->query.heads)
    return AKV_QUANT_SELECT_SHAPE;
  qbs_profile_binding_t binding;
  if ((p->key_encoding != QBS_WEIGHT_ENCODING_Q4_0 &&
       p->key_encoding != QBS_WEIGHT_ENCODING_Q8_0_WEIGHT) ||
      p->value_encoding != QBS_WEIGHT_ENCODING_Q8_0_WEIGHT ||
      qbs_device_bind_encodings(p->device, p->key_encoding, QBS_ACTIVATION_ENCODING_Q8_0,
                               &binding) != QBS_STATUS_OK)
    return AKV_QUANT_SELECT_CAPABILITY;
  const size_t key_row = (dim / 32u) * (p->key_encoding == QBS_WEIGHT_ENCODING_Q4_0 ? 18u : 34u);
  const size_t quant_row = (dim / 32u) * 34u;
  if (!akv_quant_view_valid(&p->query, dim * sizeof(float), sizeof(float)) ||
      !akv_quant_view_valid(&p->key, key_row, 2) ||
      !akv_quant_view_valid(&p->value, quant_row, 2) ||
      !akv_quant_view_valid(&p->output, dim * sizeof(float), sizeof(float)) ||
      p->key.token_stride < key_row)
    return AKV_QUANT_SELECT_LAYOUT;
  const uintptr_t mask_address = (uintptr_t)p->mask;
  if (!p->mask || mask_address % sizeof(uint16_t) ||
      p->mask_bytes < p->key.tokens * sizeof(uint16_t) ||
      p->mask_bytes > UINTPTR_MAX - mask_address)
    return AKV_QUANT_SELECT_MASK;
  const akv_quant_tensor_view_t *inputs[] = {&p->query, &p->key, &p->value};
  for (unsigned i = 0; i < 3; ++i)
    if (akv_quant_overlap(p->output.data, p->output.bytes, inputs[i]->data, inputs[i]->bytes))
      return AKV_QUANT_SELECT_ALIAS;
  if (akv_quant_overlap(p->output.data, p->output.bytes, p->mask, p->mask_bytes))
    return AKV_QUANT_SELECT_ALIAS;
  unsigned visible = 0, hidden = 0;
  for (unsigned token = 0; token < p->key.tokens; ++token) {
    uint16_t bits;
    AKV_QUANT_FIELD_COPY(&bits, (const unsigned char *)p->mask + token * sizeof(bits), sizeof(bits));
    if (bits == UINT16_C(0xfc00)) hidden = 1;
    else if (bits == 0 && !hidden) ++visible;
    else return AKV_QUANT_SELECT_MASK;
  }
  if (!visible) return AKV_QUANT_SELECT_MASK;
  const unsigned heads = p->query.heads / p->key.heads;
  const unsigned m = heads >= 4 ? 4 : heads >= 2 ? 2 : 1;
  const unsigned n = visible < 32 ? visible : 32;
  const qbs_capabilities_t *caps = &p->device->capabilities;
  if (!caps->valid || caps->architecture_version != QBS_ARCH_VERSION ||
      caps->descriptor_version != QBS_DESCRIPTOR_VERSION || caps->descriptor_bytes != QBS_DESCRIPTOR_BYTES ||
      caps->numerical_contract_version != QBS_NUMERICAL_CONTRACT_VERSION ||
      caps->max_m < m || caps->max_n < n || caps->max_k_blocks < dim / 32u ||
      caps->max_results < m * n || caps->result_element_bits != 32 ||
      !caps->blocking_completion || !caps->fault_atomic_destination ||
      caps->descriptor_alignment_log2 > 6 || caps->weight_alignment_log2 > 1 ||
      caps->activation_alignment_log2 > 6 ||
      !(caps->weight_layouts & (1u << QBS_WEIGHT_LAYOUT_ROW_MAJOR)) ||
      !(caps->activation_layouts & (1u << QBS_ACTIVATION_LAYOUT_ROW_MAJOR)))
    return AKV_QUANT_SELECT_CAPABILITY;
  /* QBS validates the command base, not every internal block/row address.
   * Packed Q8_0 rows can be 34 bytes; check actual groups4/2/1 starts rather
   * than falsely requiring each row to meet base alignment independently. */
  for (unsigned first = 0; first < heads;) {
    if ((first * quant_row) & (((size_t)1u << caps->activation_alignment_log2) - 1u))
      return AKV_QUANT_SELECT_CAPABILITY;
    const unsigned remaining = heads - first;
    first += remaining >= 4 ? 4 : remaining >= 2 ? 2 : 1;
  }
  for (unsigned head = 0; head < p->query.heads; ++head)
    for (unsigned block = 0; block < dim / 32u; ++block) {
      uint32_t maximum = 0;
      for (unsigned d = 0; d < 32; ++d) {
        uint32_t bits;
        AKV_QUANT_FIELD_COPY(&bits, (const unsigned char *)p->query.data + head * p->query.head_stride +
                          (block * 32u + d) * 4u, 4);
        bits &= UINT32_C(0x7fffffff);
        if ((bits & UINT32_C(0x7f800000)) == UINT32_C(0x7f800000)) return AKV_QUANT_SELECT_NONFINITE;
        if (bits > maximum) maximum = bits;
      }
      /* Conservative source-domain guard for the original Q8_0 quantizer:
       * nonzero amax >= 2^-120 keeps reciprocal finite; amax <= 127*65504
       * keeps its rounded F16 scale finite. Zero blocks use its id=0 branch.
       * Bit comparisons avoid raising FP flags during fallback selection. */
      if (maximum && (maximum < UINT32_C(0x03800000) || maximum > UINT32_C(0x4afde040)))
        return AKV_QUANT_SELECT_QUERY_RANGE;
    }
  for (unsigned which = 0; which < 2; ++which) {
    const akv_quant_tensor_view_t *view = which ? &p->value : &p->key;
    const unsigned block_bytes = which || p->key_encoding == QBS_WEIGHT_ENCODING_Q8_0_WEIGHT ? 34u : 18u;
    for (unsigned head = 0; head < view->heads; ++head)
      for (unsigned token = 0; token < visible; ++token)
        for (unsigned block = 0; block < dim / 32u; ++block) {
          uint16_t bits;
          AKV_QUANT_FIELD_COPY(&bits, (const unsigned char *)view->data + head * view->head_stride +
                           token * view->token_stride + block * block_bytes, 2);
          if ((bits & UINT16_C(0x7c00)) == UINT16_C(0x7c00)) return AKV_QUANT_SELECT_NONFINITE;
        }
  }
  const akv_quant_selection_t result = {heads, p->key.heads, dim, visible,
      binding.weight_profile, key_row, quant_row};
  *selection = result;
  return AKV_QUANT_SELECT_OK;
}

#endif
