/* Reuse frozen primitives, output guards and comparison helpers, not its main
 * or contiguous input callbacks. Both live schedules read the same strided KV. */
#include "software/akv/experimental/quantized_kv/ggml_decode.h"
#include "software/akv/experimental/quantized_kv/runtime_strided.h"
#include "software/akv/experimental/quantized_kv/q8_0_value.h"
#define main archived_main
#include "attention_main.c"
#undef main

extern const unsigned char attention_strided_key[], attention_strided_value[];
extern const uint16_t attention_mask[];
static struct ggml_tensor strided_q, strided_k, strided_v, strided_mask, strided_dst;
static unsigned char strided_scratch[16384] __attribute__((aligned(64)));
static float shared_previous[HEADS][DIM];

static __attribute__((noinline)) void strided_value_decode(const void *source,
    float *destination, int64_t elements) {
  akv_quant_q8_0_value(source, destination, (size_t)elements);
}

static int strided_baseline_qk(void *opaque, unsigned first_head, unsigned heads,
    unsigned first_token, unsigned tokens, float *scores, size_t stride) {
  context_t *c = opaque;
  if (heads != 1 || tokens != 1 || first_head >= HEADS || first_token >= TOKENS || stride < tokens)
    return 1;
  ++c->calls;
  const unsigned row = attention_key_kind ? 72 : 136;
  const void *key_row = attention_strided_key + first_token * 2u * row;
  if (attention_key_kind)
    ggml_vec_dot_q4_0_q8_0(DIM, scores, 0, key_row, 0, c->query[first_head], 0, 1);
  else
    ggml_vec_dot_q8_0_q8_0(DIM, scores, 0, key_row, 0, c->query[first_head], 0, 1);
  return 0;
}

static int strided_baseline_value(void *opaque, unsigned token, float *destination, unsigned dim) {
  context_t *c = opaque;
  if (token >= TOKENS || dim != DIM) return 1;
  ++c->values;
  strided_value_decode(attention_strided_value + token * 272u, destination, dim);
  return 0;
}

static uint64_t strided_cycles(void) {
  uint64_t result;
  __asm__ volatile("rdcycle %0" : "=r"(result) : : "memory");
  return result;
}

static void strided_tensor(struct ggml_tensor *t, enum ggml_type type, const void *data,
    unsigned d, unsigned tokens, unsigned heads, size_t block, size_t row, size_t head, size_t span) {
  memset(t, 0, sizeof(*t));
  t->type=type; t->data=(void *)data;
  t->ne[0]=d; t->ne[1]=tokens; t->ne[2]=heads; t->ne[3]=1;
  t->nb[0]=block; t->nb[1]=row; t->nb[2]=head; t->nb[3]=span;
}

