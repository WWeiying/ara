#include "software/akv/experimental/quantized_kv/selection.h"
#include <assert.h>
#include <fenv.h>
#include <stdio.h>

static float queries[32 * 260] __attribute__((aligned(64)));
static float outputs[32 * 264] __attribute__((aligned(64)));
static unsigned char keys[4 * 128 * 8 * 34] __attribute__((aligned(64)));
static unsigned char values[4 * 128 * 8 * 34] __attribute__((aligned(64)));
static uint16_t mask[128] __attribute__((aligned(64)));
static qbs_device_t device;
static unsigned accepted, rejected;

static unsigned check_view_interval_proof(void) {
  unsigned cases = 0;
  for (unsigned heads=1; heads<=4; ++heads)
    for (unsigned tokens=1; tokens<=4; ++tokens)
      for (size_t row=2; row<=8; row+=2)
        for (size_t ts=2; ts<=32; ts+=2)
          for (size_t hs=2; hs<=64; hs+=2) {
            const akv_quant_tensor_view_t view = {(void *)(uintptr_t)0x10000,
                4096, ts, hs, 32, tokens, heads};
            if (akv_quant_view_valid(&view, row, 2)) {
              for (unsigned a=0; a<heads*tokens; ++a)
                for (unsigned b=a+1; b<heads*tokens; ++b) {
                  const size_t x=(a/tokens)*hs+(a%tokens)*ts;
                  const size_t y=(b/tokens)*hs+(b%tokens)*ts;
                  assert(x+row<=y || y+row<=x);
                  assert(x+row<=view.bytes && y+row<=view.bytes);
                }
            }
            ++cases;
          }
  return cases;
}

static akv_quant_selection_input_t input(unsigned dim, unsigned groups,
    unsigned kv_heads, unsigned visible, unsigned q4, unsigned interleaved_v) {
  const size_t key_row = dim / 32u * (q4 ? 18u : 34u);
  const size_t value_row = dim / 32u * 34u;
  const unsigned heads = groups * kv_heads;
  for (unsigned t = 0; t < 128; ++t) mask[t] = t < visible ? 0 : UINT16_C(0xfc00);
  akv_quant_selection_input_t p = {
    .requested=1, .vlen_bits=1024, .vstart=0, .normal_memory=1, .device=&device,
    .key_encoding=q4 ? QBS_WEIGHT_ENCODING_Q4_0 : QBS_WEIGHT_ENCODING_Q8_0_WEIGHT,
    .value_encoding=QBS_WEIGHT_ENCODING_Q8_0_WEIGHT,
    .query={queries, heads*(dim+4u)*4u, dim*4u, (dim+4u)*4u, dim, 1, heads},
    .key={keys, 128*kv_heads*key_row, key_row, 128*key_row, dim, 128, kv_heads},
    .value={values, 128*kv_heads*value_row,
      interleaved_v ? kv_heads*value_row : value_row,
      interleaved_v ? value_row : 128*value_row, dim, 128, kv_heads},
    .output={outputs, heads*(dim+8u)*4u, dim*4u, (dim+8u)*4u, dim, 1, heads},
    .mask=mask, .mask_bytes=sizeof(mask), .scale=0.0883883461356163f,
  };
  return p;
}

static void rejected_unchanged(akv_quant_selection_input_t *p, int reason) {
  akv_quant_selection_t selection, before;
  memset(&selection, 0xa5, sizeof(selection));
  memcpy(&before, &selection, sizeof(before));
  assert(akv_quant_select(p, &selection) == reason);
  assert(memcmp(&before, &selection, sizeof(before)) == 0);
  ++rejected;
}

int main(void) {
  const unsigned view_cases = check_view_interval_proof();
  assert(qbs_device_init_reference(1024, &device) == QBS_STATUS_OK);
  memset(outputs, 0xa5, sizeof(outputs));
  const unsigned prefixes[] = {1, 31, 32, 33, 63, 64, 65, 128};
  for (unsigned dim = 32; dim <= 256; dim += 32)
    for (unsigned groups = 1; groups <= 8; ++groups)
      for (unsigned kv_heads = 1; kv_heads <= 4; ++kv_heads)
        for (unsigned i = 0; i < sizeof(prefixes)/sizeof(prefixes[0]); ++i)
          for (unsigned q4 = 0; q4 < 2; ++q4)
            for (unsigned interleaved = 0; interleaved < 2; ++interleaved) {
              akv_quant_selection_input_t p = input(dim, groups, kv_heads, prefixes[i], q4, interleaved);
              akv_quant_selection_t selected;
              assert(akv_quant_select(&p, &selected) == AKV_QUANT_SELECT_OK);
              assert(selected.group_heads == groups && selected.kv_heads == kv_heads &&
                     selected.dim == dim && selected.visible_tokens == prefixes[i] &&
                     selected.key_row_bytes == dim/32*(q4 ? 18u : 34u) &&
                     selected.query_quant_row_bytes == dim/32*34u &&
                     selected.key_profile == (q4 ? QBS_WEIGHT_PROFILE_Q4_0 : QBS_WEIGHT_PROFILE_Q8_0_WEIGHT));
              ++accepted;
            }
  akv_quant_selection_input_t p;
#define RESET() p = input(128, 6, 2, 65, 0, 0)
#define REJECT(change, reason) do { RESET(); change; rejected_unchanged(&p, reason); } while (0)
  REJECT(p.requested=0, AKV_QUANT_SELECT_DISABLED);
  REJECT(p.requested=2, AKV_QUANT_SELECT_DISABLED);
  REJECT(p.device=NULL, AKV_QUANT_SELECT_CAPABILITY);
  REJECT(p.vlen_bits=256, AKV_QUANT_SELECT_CAPABILITY);
  REJECT(p.vstart=1, AKV_QUANT_SELECT_CAPABILITY);
  REJECT(p.frm=1, AKV_QUANT_SELECT_CAPABILITY);
  REJECT(p.normal_memory=0, AKV_QUANT_SELECT_CAPABILITY);
  REJECT(p.scale=0.0f, AKV_QUANT_SELECT_FEATURE);
  REJECT(p.scale=-1.0f, AKV_QUANT_SELECT_FEATURE);
  REJECT(p.scale=0x1p65f, AKV_QUANT_SELECT_FEATURE);
  REJECT(p.softcap=1.0f, AKV_QUANT_SELECT_FEATURE);
  REJECT(p.max_bias=1.0f, AKV_QUANT_SELECT_FEATURE);
  REJECT(p.sinks_present=1, AKV_QUANT_SELECT_FEATURE);
  REJECT(p.query.dim=127, AKV_QUANT_SELECT_SHAPE);
  REJECT(p.query.tokens=2, AKV_QUANT_SELECT_SHAPE);
  REJECT(p.query.heads=11, AKV_QUANT_SELECT_SHAPE);
  REJECT(p.query.heads=18, AKV_QUANT_SELECT_SHAPE);
  REJECT(p.key.tokens=65537, AKV_QUANT_SELECT_SHAPE);
  REJECT(p.value.dim=64, AKV_QUANT_SELECT_SHAPE);
  REJECT(p.output.heads=11, AKV_QUANT_SELECT_SHAPE);
  REJECT(p.key_encoding=UINT64_MAX, AKV_QUANT_SELECT_CAPABILITY);
  REJECT(p.value_encoding=QBS_WEIGHT_ENCODING_Q4_0, AKV_QUANT_SELECT_CAPABILITY);
  REJECT(p.query.bytes=4, AKV_QUANT_SELECT_LAYOUT);
  REJECT(p.query.data=(void *)((uintptr_t)queries+1), AKV_QUANT_SELECT_LAYOUT);
  REJECT(p.query.bytes=SIZE_MAX, AKV_QUANT_SELECT_LAYOUT);
  REJECT(p.query.head_stride=SIZE_MAX-3, AKV_QUANT_SELECT_LAYOUT);
  REJECT(p.key.token_stride+=2, AKV_QUANT_SELECT_LAYOUT);
  REJECT(p.key.head_stride=136, AKV_QUANT_SELECT_LAYOUT);
  REJECT(p.value.token_stride=134, AKV_QUANT_SELECT_LAYOUT);
  REJECT(p.value.head_stride=136, AKV_QUANT_SELECT_LAYOUT);
  REJECT(p.mask=NULL, AKV_QUANT_SELECT_MASK);
  REJECT(p.mask_bytes=2, AKV_QUANT_SELECT_MASK);
  REJECT(mask[66]=0, AKV_QUANT_SELECT_MASK);
  REJECT(mask[0]=0x8000, AKV_QUANT_SELECT_MASK);
  REJECT(mask[0]=0x7e00, AKV_QUANT_SELECT_MASK);
  REJECT(for (unsigned i=0;i<128;++i) mask[i]=0xfc00, AKV_QUANT_SELECT_MASK);
  REJECT(p.output.data=p.query.data, AKV_QUANT_SELECT_ALIAS);
  REJECT(p.output.data=p.key.data, AKV_QUANT_SELECT_ALIAS);
  REJECT(p.output.data=p.value.data, AKV_QUANT_SELECT_ALIAS);
  /* Alias the mask from inside a valid output allocation without reading it. */
  REJECT(p.mask=(const uint16_t *)outputs, AKV_QUANT_SELECT_ALIAS);
  const uint32_t snan = UINT32_C(0x7f800001);
  RESET(); memcpy(&p.scale, &snan, 4); feclearexcept(FE_ALL_EXCEPT);
  rejected_unchanged(&p, AKV_QUANT_SELECT_FEATURE);
  assert(!fetestexcept(FE_INVALID));
  RESET(); memcpy(queries, &snan, 4); feclearexcept(FE_ALL_EXCEPT);
  rejected_unchanged(&p, AKV_QUANT_SELECT_NONFINITE);
  assert(!fetestexcept(FE_INVALID)); memset(queries, 0, sizeof(queries));
  const uint32_t query_range_cases[] = {0x00000001u, 0x037fffffu, 0x4afde041u, 0x7f7fffffu};
  for (unsigned i=0; i<sizeof(query_range_cases)/sizeof(query_range_cases[0]); ++i) {
    RESET(); memcpy(queries, &query_range_cases[i], 4);
    rejected_unchanged(&p, AKV_QUANT_SELECT_QUERY_RANGE);
  }
  const uint32_t valid_query_limits[] = {0x03800000u, 0x4afde040u};
  for (unsigned i=0; i<sizeof(valid_query_limits)/sizeof(valid_query_limits[0]); ++i) {
    RESET(); memcpy(queries, &valid_query_limits[i], 4);
    akv_quant_selection_t range_selection;
    assert(akv_quant_select(&p, &range_selection) == AKV_QUANT_SELECT_OK);
    ++accepted;
  }
  memset(queries, 0, sizeof(queries));
  const uint16_t nan_scale=UINT16_C(0x7c01);
  RESET(); memcpy(keys, &nan_scale, 2);
  rejected_unchanged(&p, AKV_QUANT_SELECT_NONFINITE); memset(keys, 0, sizeof(keys));
  RESET(); memcpy(values, &nan_scale, 2);
  rejected_unchanged(&p, AKV_QUANT_SELECT_NONFINITE); memset(values, 0, sizeof(values));
  /* Uninitialized/nonfinite hidden rows are not read as model input. */
  RESET(); memcpy(keys+65*136, &nan_scale, 2); memcpy(values+65*136, &nan_scale, 2);
  akv_quant_selection_t selected;
  assert(akv_quant_select(&p, &selected) == AKV_QUANT_SELECT_OK); ++accepted;
  memset(keys, 0, sizeof(keys)); memset(values, 0, sizeof(values));
  qbs_device_t limited;
#define CAP_REJECT(change) do { RESET(); limited=device; p.device=&limited; change; \
  rejected_unchanged(&p, AKV_QUANT_SELECT_CAPABILITY); } while (0)
  CAP_REJECT(limited.capabilities.max_m=2);
  CAP_REJECT(limited.capabilities.architecture_version=99);
  CAP_REJECT(limited.capabilities.descriptor_bytes=0);
  CAP_REJECT(limited.capabilities.max_n=31);
  CAP_REJECT(limited.capabilities.max_k_blocks=3);
  CAP_REJECT(limited.capabilities.max_results=127);
  CAP_REJECT(limited.capabilities.blocking_completion=0);
  CAP_REJECT(limited.capabilities.fault_atomic_destination=0);
  CAP_REJECT(limited.capabilities.weight_alignment_log2=4);
  CAP_REJECT(limited.capabilities.activation_alignment_log2=7);
  CAP_REJECT(limited.capabilities.activation_alignment_log2=6);
  CAP_REJECT(limited.capabilities.descriptor_alignment_log2=7);
  CAP_REJECT(limited.capabilities.result_element_bits=16);
  CAP_REJECT(limited.capabilities.weight_layouts=0);
  CAP_REJECT(limited.capabilities.activation_layouts=0);
  CAP_REJECT(limited.capabilities.numerical_contract_version=99);
  CAP_REJECT(limited.weight_profiles=0);
  for (size_t i=0; i<sizeof(outputs); ++i) assert(((unsigned char *)outputs)[i] == 0xa5);
  printf("QUANT_SELECTION_HOST_PASS accepted=%u rejected=%u view_cases=%u output_untouched=1 hidden_rows_skipped=1 snan_no_invalid=1\n",
         accepted, rejected, view_cases);
  return 0;
}
