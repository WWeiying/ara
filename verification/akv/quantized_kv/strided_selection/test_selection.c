#include "software/akv/experimental/quantized_kv/selection_strided.h"
#include <assert.h>
#include <fenv.h>
#include <stdio.h>
#include <stdlib.h>

enum { DIM = 128, TOKENS = 128, KV_HEADS = 2, Q_HEADS = 12 };
static float query[DIM * Q_HEADS] __attribute__((aligned(64)));
static float output[DIM * Q_HEADS] __attribute__((aligned(64)));
static unsigned char key[KV_HEADS * TOKENS * 136] __attribute__((aligned(64)));
static unsigned char value[KV_HEADS * TOKENS * 136] __attribute__((aligned(64)));
static unsigned char strided[KV_HEADS * TOKENS * 160 + 64] __attribute__((aligned(64)));
static uint16_t mask[TOKENS] __attribute__((aligned(64)));
static qbs_device_t device;
static unsigned accepted, rejected;

static void same_plan(const akv_quant_selection_t *a, const akv_quant_selection_t *b) {
  assert(a->group_heads == b->group_heads && a->kv_heads == b->kv_heads &&
         a->dim == b->dim && a->visible_tokens == b->visible_tokens &&
         a->key_profile == b->key_profile && a->key_row_bytes == b->key_row_bytes &&
         a->query_quant_row_bytes == b->query_quant_row_bytes);
}

static akv_quant_selection_t check(const akv_quant_selection_input_t *p, int successor, int expected) {
  akv_quant_selection_t result, before;
  memset(&result, 0xa5, sizeof(result));
  memcpy(&before, &result, sizeof(before));
  const int status = successor ? akv_quant_select_strided(p, &result) : akv_quant_select(p, &result);
  if (status != expected) fprintf(stderr, "selection status=%d expected=%d successor=%d\n", status, expected, successor);
  assert(status == expected);
  if (status) {
    assert(memcmp(&before, &result, sizeof(before)) == 0);
    ++rejected;
  } else ++accepted;
  return result;
}

static akv_quant_selection_input_t input(unsigned q4, unsigned visible, unsigned layout) {
  const size_t row = q4 ? 72 : 136;
  size_t ts = row, hs = TOKENS * row;
  if (layout == 1) { ts = 2 * row; hs = row; }
  if (layout == 2) { ts = row + 8; hs = TOKENS * ts + 16; }
  if (layout == 3) { hs = row + 8; ts = 2 * hs + 16; }
  const size_t extent = hs + (TOKENS - 1) * ts + row;
  assert(extent <= sizeof(strided));
  if (layout) {
    /* Nonfinite half patterns in gaps make accidental scale scans fail. */
    memset(strided, 0x7c, sizeof(strided));
    for (unsigned h = 0; h < KV_HEADS; ++h)
      for (unsigned t = 0; t < TOKENS; ++t) {
        memcpy(strided + h * hs + t * ts, key + (h * TOKENS + t) * row, row);
        assert(memcmp(strided + h * hs + t * ts, key + (h * TOKENS + t) * row, row) == 0);
      }
  }
  for (unsigned t = 0; t < TOKENS; ++t) mask[t] = t < visible ? 0 : UINT16_C(0xfc00);
  akv_quant_selection_input_t p = {
    .requested=1, .vlen_bits=1024, .normal_memory=1, .device=&device,
    .key_encoding=q4 ? QBS_WEIGHT_ENCODING_Q4_0 : QBS_WEIGHT_ENCODING_Q8_0_WEIGHT,
    .value_encoding=QBS_WEIGHT_ENCODING_Q8_0_WEIGHT,
    .query={query, sizeof(query), DIM*4, DIM*4, DIM, 1, Q_HEADS},
    .key={layout ? strided : key, extent, ts, hs, DIM, TOKENS, KV_HEADS},
    .value={value, sizeof(value), 136, TOKENS*136, DIM, TOKENS, KV_HEADS},
    .output={output, sizeof(output), DIM*4, DIM*4, DIM, 1, Q_HEADS},
    .mask=mask, .mask_bytes=sizeof(mask), .scale=0.0883883461356163f,
  };
  if (!q4 && layout == 1) assert(ts == 272 && hs == 136 && extent == 34816);
  return p;
}

static void compare_layouts(unsigned q4) {
  const unsigned prefixes[] = {1, 7, 31, 32, 33, 63, 64, 65, 127, 128};
  for (unsigned i = 0; i < sizeof(prefixes)/sizeof(prefixes[0]); ++i) {
    akv_quant_selection_input_t p = input(q4, prefixes[i], 0);
    const akv_quant_selection_t reference = check(&p, 0, AKV_QUANT_SELECT_OK);
    assert(reference.group_heads == 6 && reference.kv_heads == 2 && reference.dim == 128 &&
           reference.visible_tokens == prefixes[i] && reference.key_row_bytes == (q4 ? 72u : 136u) &&
           reference.query_quant_row_bytes == 136);
    for (unsigned layout = 0; layout < 4; ++layout) {
      p = input(q4, prefixes[i], layout);
      const akv_quant_selection_t actual = check(&p, 1, AKV_QUANT_SELECT_OK);
      same_plan(&reference, &actual);
      if (layout) check(&p, 0, AKV_QUANT_SELECT_LAYOUT);
    }
  }
}

static void initialize(unsigned q4) {
  const unsigned block = q4 ? 18 : 34;
  for (unsigned i = 0; i < DIM*Q_HEADS; ++i) query[i] = (float)((int)(i % 31) - 15) / 32;
  memset(key, 0x12, sizeof(key));
  memset(value, 0x23, sizeof(value));
  const uint16_t scale = UINT16_C(0x3000);
  for (unsigned i = 0; i < KV_HEADS*TOKENS*4; ++i) {
    memcpy(key + i*block, &scale, 2);
    memcpy(value + i*34, &scale, 2);
  }
}

static void rejection_matrix(unsigned q4) {
  akv_quant_selection_input_t p, normalized;
#define RESET() do { initialize(q4); normalized=input(q4, 65, 0); p=input(q4, 65, 1); } while (0)
#define REJECT(change, reason) do { RESET(); change; check(&p, 1, reason); } while (0)
  REJECT(p.key.bytes--, AKV_QUANT_SELECT_LAYOUT);
  REJECT(p.key.data=strided+1, AKV_QUANT_SELECT_LAYOUT);
  REJECT(p.key.data=NULL, AKV_QUANT_SELECT_LAYOUT);
  REJECT(p.key.token_stride=(q4 ? 72u : 136u)-2, AKV_QUANT_SELECT_LAYOUT);
  REJECT(p.key.token_stride-=2, AKV_QUANT_SELECT_LAYOUT);
  REJECT(p.key.head_stride-=2, AKV_QUANT_SELECT_LAYOUT);
  REJECT(p.key.token_stride=SIZE_MAX-1, AKV_QUANT_SELECT_LAYOUT);
  REJECT(p.key.head_stride=SIZE_MAX-1, AKV_QUANT_SELECT_LAYOUT);
  REJECT(p.key.bytes=SIZE_MAX, AKV_QUANT_SELECT_LAYOUT);
  REJECT(p.key.data=(void *)(UINTPTR_MAX-1), AKV_QUANT_SELECT_LAYOUT);
#define BOTH(change, reason) do { RESET(); change; check(&normalized, 0, reason); check(&p, 1, reason); } while (0)
  BOTH(p.requested=normalized.requested=0, AKV_QUANT_SELECT_DISABLED);
  BOTH(p.frm=normalized.frm=1, AKV_QUANT_SELECT_CAPABILITY);
  BOTH(p.vstart=normalized.vstart=1, AKV_QUANT_SELECT_CAPABILITY);
  BOTH(p.normal_memory=normalized.normal_memory=0, AKV_QUANT_SELECT_CAPABILITY);
  BOTH(p.device=normalized.device=NULL, AKV_QUANT_SELECT_CAPABILITY);
  BOTH(p.query.heads=normalized.query.heads=11, AKV_QUANT_SELECT_SHAPE);
  BOTH(p.scale=normalized.scale=0, AKV_QUANT_SELECT_FEATURE);
  BOTH(p.softcap=normalized.softcap=1, AKV_QUANT_SELECT_FEATURE);
  BOTH(p.output.data=normalized.output.data=query, AKV_QUANT_SELECT_ALIAS);
  BOTH(p.output.data=p.key.data; normalized.output.data=normalized.key.data, AKV_QUANT_SELECT_ALIAS);
  BOTH(p.mask=normalized.mask=(const uint16_t *)output, AKV_QUANT_SELECT_ALIAS);
  BOTH(p.mask_bytes=normalized.mask_bytes=2, AKV_QUANT_SELECT_MASK);
  BOTH(mask[66]=0, AKV_QUANT_SELECT_MASK);
  BOTH(mask[0]=UINT16_C(0x8000), AKV_QUANT_SELECT_MASK);
  BOTH(mask[0]=UINT16_C(0x7c01), AKV_QUANT_SELECT_MASK);
  BOTH(for (unsigned i=0; i<TOKENS; ++i) mask[i]=UINT16_C(0xfc00), AKV_QUANT_SELECT_MASK);
  const uint32_t snan = UINT32_C(0x7f800001);
  RESET(); memcpy(query, &snan, 4);
  feclearexcept(FE_ALL_EXCEPT); feraiseexcept(FE_DIVBYZERO);
  check(&normalized, 0, AKV_QUANT_SELECT_NONFINITE);
  check(&p, 1, AKV_QUANT_SELECT_NONFINITE);
  assert(fetestexcept(FE_ALL_EXCEPT) == FE_DIVBYZERO);
  const uint32_t tiny = 1;
  RESET(); memset(query, 0, sizeof(query)); memcpy(query, &tiny, 4);
  check(&normalized, 0, AKV_QUANT_SELECT_QUERY_RANGE);
  check(&p, 1, AKV_QUANT_SELECT_QUERY_RANGE);
  const uint16_t nan_scale = UINT16_C(0x7c01);
  for (unsigned which = 0; which < 2; ++which) {
    for (unsigned t = 64; t <= 65; ++t) {
      RESET();
      const size_t row = which ? 136 : (q4 ? 72 : 136);
      /* Head 1, final visible/first hidden token, last quantization block. */
      unsigned char *base = which ? value : key;
      memcpy(base + (TOKENS+t)*row + 3*(row/4), &nan_scale, 2);
      p = input(q4, 65, 1);
      const int expected = t == 64 ? AKV_QUANT_SELECT_NONFINITE : AKV_QUANT_SELECT_OK;
      check(&normalized, 0, expected);
      check(&p, 1, expected);
    }
  }
#undef BOTH
#undef REJECT
#undef RESET
}

static void load(const char *path, void *destination, size_t bytes) {
  FILE *file = fopen(path, "rb");
  assert(file && fseek(file, 0, SEEK_END) == 0 && ftell(file) == (long)bytes);
  rewind(file);
  assert(fread(destination, 1, bytes, file) == bytes && fclose(file) == 0);
}

int main(int argc, char **argv) {
  assert(qbs_device_init_reference(1024, &device) == QBS_STATUS_OK);
  memset(output, 0xa5, sizeof(output));
  if (argc == 1) {
    for (unsigned q4=0; q4<2; ++q4) {
      initialize(q4);
      compare_layouts(q4);
      rejection_matrix(q4);
    }
  } else {
    assert(argc == 5 && (!strcmp(argv[1], "0") || !strcmp(argv[1], "1")));
    const unsigned q4 = argv[1][0] == '1';
    load(argv[2], query, sizeof(query));
    load(argv[3], key, KV_HEADS*TOKENS*(q4 ? 72u : 136u));
    load(argv[4], value, sizeof(value));
    compare_layouts(q4);
  }
  for (size_t i=0; i<sizeof(output); ++i) assert(((unsigned char *)output)[i] == 0xa5);
  printf("STRIDED_SELECTION_HOST_PASS accepted=%u rejected=%u real_derived=%u output_untouched=1 native_execution=0\n",
         accepted, rejected, argc != 1);
  return 0;
}
