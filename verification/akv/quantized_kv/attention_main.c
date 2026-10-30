#include "qbs/qbs.h"
#include "printf.h"
#include "software/akv/experimental/quantized_kv/online.h"
#include <stdint.h>
#include <string.h>

/* One original GQA group, all six Query heads and all 128 visible tokens.
 * The builder binds these symbols and the exact scale to the frozen capture. */
extern const float attention_query[], attention_golden[], attention_scale;
extern const unsigned char attention_key[], attention_value[];
extern const unsigned attention_key_kind;
extern void quantize_row_q8_0(const float *, void *, int64_t);
extern void dequantize_row_q8_0(const void *, float *, int64_t);
extern void ggml_vec_dot_q8_0_q8_0(int, float *, size_t, const void *, size_t,
                                 const void *, size_t, int);
extern void ggml_vec_dot_q4_0_q8_0(int, float *, size_t, const void *, size_t,
                                 const void *, size_t, int);
extern void quant_kv_ggml_mad_f32(int, float *, const float *, float);
extern void quant_kv_ggml_scale_f32(int, float *, float);

enum { HEADS = 6, DIM = 128, TOKENS = 128, STRIDE = 136 };
typedef struct {
  unsigned shared, calls, values, errors;
  unsigned char query[HEADS][STRIDE] __attribute__((aligned(64)));
  qbs_descriptor_t descriptor __attribute__((aligned(64)));
} context_t;

static context_t context;
static akv_quant_online_workspace_t workspace;
static struct __attribute__((aligned(64))) {
  unsigned char before[64];
  float data[HEADS][STRIDE];
  unsigned char after[64];
} output;
static float baseline[HEADS][DIM];

static uint32_t bits(float value) {
  uint32_t result;
  memcpy(&result, &value, sizeof(result));
  return result;
}

static uint64_t cycles(void) {
  uint64_t value;
  __asm__ volatile("rdcycle %0" : "=r"(value));
  return value;
}

static void drain(void) {
  __asm__ volatile("vmv.x.s zero,v8\nfence rw,rw" : : : "memory");
}

static int qk(void *opaque, unsigned first_head, unsigned heads,
              unsigned first_token, unsigned tokens, float *scores, size_t stride) {
  context_t *c = opaque;
  const unsigned row_bytes = attention_key_kind ? 72 : 136;
  if (first_head + heads > HEADS || first_token + tokens > TOKENS ||
      !heads || !tokens || tokens > 32 || stride < tokens) return 1;
  ++c->calls;
  if (!c->shared) {
    if (heads != 1 || tokens != 1) return 1;
    if (attention_key_kind)
      ggml_vec_dot_q4_0_q8_0(DIM, scores, 0, attention_key + first_token * row_bytes,
                            0, c->query[first_head], 0, 1);
    else
      ggml_vec_dot_q8_0_q8_0(DIM, scores, 0, attention_key + first_token * row_bytes,
                            0, c->query[first_head], 0, 1);
    return 0;
  }
  qbs_descriptor_fields_t fields = {0};
  fields.descriptor_version = QBS_DESCRIPTOR_VERSION;
  fields.weight_profile = attention_key_kind ? QBS_WEIGHT_PROFILE_Q4_0 : QBS_WEIGHT_PROFILE_Q8_0_WEIGHT;
  fields.activation_profile = QBS_ACTIVATION_PROFILE_Q8_0;
  fields.weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR;
  fields.activation_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR;
  fields.activation_access = QBS_ACTIVATION_ACCESS_DIRECT;
  fields.n = tokens;
  fields.k_blocks = DIM / 32;
  c->descriptor.header = qbs_pack_descriptor_header(&fields);
  c->descriptor.weight_base = (uintptr_t)(attention_key + first_token * row_bytes);
  const qbs_status_t status = qbs_native_execute_command(NULL, &c->descriptor, heads,
      c->query[first_head], scores, stride, tokens, 0);
  return status != QBS_STATUS_OK;
}

static int value(void *opaque, unsigned token, float *out, unsigned dim) {
  context_t *c = opaque;
  if (token >= TOKENS || dim != DIM) return 1;
  ++c->values;
  dequantize_row_q8_0(attention_value + token * STRIDE, out, DIM);
  return 0;
}

int main(void) {
  qbs_device_t device;
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
  if (vlenb != 128 || qbs_device_query(qbs_native_info, NULL, &device) != QBS_STATUS_OK ||
      !(device.weight_profiles & (1u << QBS_WEIGHT_PROFILE_Q8_0_WEIGHT)) ||
      !(device.weight_profiles & (1u << QBS_WEIGHT_PROFILE_Q4_0))) return 1;
  printf("QUANT_ATTN_CAP kind=%u heads=6 d=128 visible=128 kv_head=0 trials=4 scale=%08x\n",
         attention_key_kind, bits(attention_scale));
  const unsigned order[] = {0, 1, 1, 0};
  unsigned total_errors = 0;
  for (unsigned trial = 0; trial < 4; ++trial) {
    memset(&output, 0xa5, sizeof(output));
    memset(&context, 0, sizeof(context));
    context.shared = order[trial];
    printf("QUANT_ATTN_BEGIN trial=%u shared=%u\n", trial, context.shared);
    __asm__ volatile("csrwi fcsr,0; csrwi vcsr,5" : : : "memory");
    drain();
    const uint64_t start = cycles();
    for (unsigned head = 0; head < HEADS; ++head)
      quantize_row_q8_0(attention_query + head * DIM, context.query[head], DIM);
    const akv_quant_online_plan_t plan = {
      .heads = HEADS, .dim = DIM, .tokens = TOKENS, .score_scale = attention_scale,
      .context = &context, .qk = qk, .value = value,
      .scale = quant_kv_ggml_scale_f32, .mad = quant_kv_ggml_mad_f32,
    };
    const int status = context.shared ?
        akv_quant_online_shared(&plan, &output.data[0][0], STRIDE, &workspace) :
        akv_quant_online_head_major(&plan, &output.data[0][0], STRIDE, &workspace);
    drain();
    const uint64_t elapsed = cycles() - start;
    uintptr_t fc, vc;
    __asm__ volatile("frcsr %0;csrr %1,vcsr" : "=r"(fc), "=r"(vc));
    unsigned errors = status != AKV_QUANT_OK || fc > 31 || vc != 5;
    errors += context.calls != (context.shared ? 8 : HEADS * TOKENS);
    errors += context.values != (context.shared ? TOKENS : HEADS * TOKENS);
    float max_abs = 0.0f, pair_max_abs = 0.0f;
    unsigned pair_bits_differ = 0;
    for (unsigned head = 0; head < HEADS; ++head) {
      for (unsigned d = 0; d < DIM; ++d) {
        const float y = output.data[head][d], gold = attention_golden[head * DIM + d];
        const float delta = fabsf(y - gold);
        errors += !isfinite(y) || !isfinite(gold) || delta > 0.004f + 0.002f * fabsf(gold);
        if (delta > max_abs) max_abs = delta;
        if (trial == 0) baseline[head][d] = y;
        else {
          const float diff = fabsf(y - baseline[head][d]);
          if (diff > pair_max_abs) pair_max_abs = diff;
          pair_bits_differ += bits(y) != bits(baseline[head][d]);
          /* Record QBS-vs-RVV numerical differences rather than requiring an
           * unsupported claim of identical scale/accumulation ordering. */
          if (!context.shared) errors += bits(y) != bits(baseline[head][d]);
        }
      }
      for (unsigned d = DIM; d < STRIDE; ++d)
        errors += bits(output.data[head][d]) != UINT32_C(0xa5a5a5a5);
    }
    for (unsigned i = 0; i < 64; ++i)
      errors += output.before[i] != 0xa5 || output.after[i] != 0xa5;
    printf("QUANT_ATTN_RESULT trial=%u shared=%u cycles=%lu calls=%u values=%u fcsr=%lu vcsr=%lu max_abs=%08x pair_max_abs=%08x pair_bits_differ=%u errors=%u hex=",
        trial, context.shared, (unsigned long)elapsed, context.calls, context.values,
        (unsigned long)fc, (unsigned long)vc, bits(max_abs), bits(pair_max_abs), pair_bits_differ, errors);
    for (unsigned head = 0; head < HEADS; ++head)
      for (unsigned d = 0; d < DIM; ++d) printf("%08x", bits(output.data[head][d]));
    printf("\n");
    total_errors += errors;
    if (errors) return 1;
  }
  printf("QUANT_ATTN_SUITE_PASS trials=4 outputs=768 golden_tolerance=1 ordinary_repeats_exact=1\n");
  return total_errors != 0;
}
