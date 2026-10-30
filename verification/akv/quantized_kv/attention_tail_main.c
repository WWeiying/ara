/* Full Attention correctness at the actual Decode tail and a panel boundary. */
#include "software/akv/experimental/quantized_kv/ggml_decode.h"
#include "software/akv/experimental/quantized_kv/runtime_strided.h"
#include "software/akv/experimental/quantized_kv/q8_0_value.h"
#define main archived_main
#include "attention_main.c"
#undef main

extern const unsigned char attention_strided_key[], attention_strided_value[];
extern const float attention_tail_gold_5[], attention_tail_gold_33[];
static struct ggml_tensor tail_q, tail_k, tail_v, tail_mask_tensor, tail_dst;
static uint16_t tail_mask[256];
static unsigned char tail_scratch[16384] __attribute__((aligned(64)));
static float previous_native[HEADS][DIM];
static unsigned visible_tokens;
static unsigned tail_trial, tail_command_seq;

static __attribute__((noinline)) void tail_value_decode(const void *source, float *destination, int64_t elements) {
  akv_quant_q8_0_value(source, destination, (size_t)elements);
}

static int tail_qk(void *opaque, unsigned head, unsigned heads, unsigned token,
    unsigned tokens, float *scores, size_t stride) {
  context_t *c = opaque;
  if (heads != 1 || tokens != 1 || head >= HEADS || token >= visible_tokens || stride < 1) return 1;
  ++c->calls;
  const unsigned row = attention_key_kind ? 72 : 136;
  const void *key = attention_strided_key + token * 2u * row;
  if (attention_key_kind)
    ggml_vec_dot_q4_0_q8_0(DIM, scores, 0, key, 0, c->query[head], 0, 1);
  else
    ggml_vec_dot_q8_0_q8_0(DIM, scores, 0, key, 0, c->query[head], 0, 1);
  return 0;
}

static int tail_value(void *opaque, unsigned token, float *destination, unsigned dim) {
  context_t *c = opaque;
  if (token >= visible_tokens || dim != DIM) return 1;
  ++c->values;
  tail_value_decode(attention_strided_value + token * 272u, destination, dim);
  return 0;
}

static qbs_status_t tail_execute(void *opaque, const qbs_descriptor_t *descriptor, unsigned m,
    const void *activation, float *scores, size_t stride, unsigned n, int segmented) {
  if (!m || m > 4 || !n || n > 32 || stride < n) return QBS_STATUS_EXECUTION;
  const qbs_status_t status = qbs_native_execute_command(opaque, descriptor, m, activation, scores, stride, n, segmented);
  if (status != QBS_STATUS_OK) return status;
  ++tail_command_seq;
  printf("QUANT_TAIL_QK visible=%u trial=%u seq=%u m=%u n=%u stride=%lu activation=",
      visible_tokens, tail_trial, tail_command_seq, m, n, (unsigned long)stride);
  const unsigned char *query = activation;
  for (unsigned i = 0; i < m * 136; ++i) printf("%02x", query[i]);
  printf(" scores=");
  for (unsigned head = 0; head < m; ++head)
    for (unsigned token = 0; token < n; ++token) printf("%08x", bits(scores[head * stride + token]));
  printf("\n");
  return status;
}

static void tensor(struct ggml_tensor *t, enum ggml_type type, const void *data,
    unsigned dim, unsigned tokens, unsigned heads, size_t block, size_t token_stride,
    size_t head_stride, size_t span) {
  memset(t, 0, sizeof(*t));
  t->type = type; t->data = (void *)data;
  t->ne[0] = dim; t->ne[1] = tokens; t->ne[2] = heads; t->ne[3] = 1;
  t->nb[0] = block; t->nb[1] = token_stride; t->nb[2] = head_stride; t->nb[3] = span;
}

int main(void) {
  __asm__ volatile("vsetivli zero,1,e32,m1,ta,ma\nvmv.v.i v8,0" : : : "v8", "memory");
  qbs_device_t device;
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));
  const size_t scratch_bytes = akv_quant_strided_workspace_bytes();
  if (vlenb != 128 || scratch_bytes != 13120 || attention_key_kind > 1 ||
      scratch_bytes > sizeof(tail_scratch) || qbs_device_query(qbs_native_info, NULL, &device) != QBS_STATUS_OK)
    return 1;
  const unsigned row = attention_key_kind ? 72 : 136;
  tensor(&tail_q, GGML_TYPE_F32, attention_query, DIM, 1, HEADS, 4, DIM * 4, DIM * 4, HEADS * DIM * 4);
  tensor(&tail_k, attention_key_kind ? GGML_TYPE_Q4_0 : GGML_TYPE_Q8_0,
      attention_strided_key, DIM, 256, 1, attention_key_kind ? 18 : 34, 2 * row, row, 512 * row);
  tensor(&tail_v, GGML_TYPE_Q8_0, attention_strided_value, DIM, 256, 1, 34, 272, 136, 69632);
  tensor(&tail_mask_tensor, GGML_TYPE_F16, tail_mask, 256, 1, 1, 2, 512, 512, 512);
  tensor(&tail_dst, GGML_TYPE_F32, output.data, DIM, HEADS, 1, 4,
      STRIDE * 4, HEADS * STRIDE * 4, sizeof(output.data));
  tail_dst.op = GGML_OP_FLASH_ATTN_EXT;
  tail_dst.src[0] = &tail_q; tail_dst.src[1] = &tail_k;
  tail_dst.src[2] = &tail_v; tail_dst.src[3] = &tail_mask_tensor;
  memcpy(tail_dst.op_params, &attention_scale, 4);
  akv_quant_ggml_context_t mapping = {0};
  mapping.requested = 1; mapping.nth = 1; mapping.normal_memory = 1;
  mapping.vlen_bits = 1024; mapping.device = &device;
  mapping.query_bytes = HEADS * DIM * 4; mapping.key_bytes = 512 * row;
  mapping.value_bytes = 69632; mapping.mask_bytes = 512; mapping.output_bytes = sizeof(output.data);
  const akv_quant_native_bindings_t bindings = {quantize_row_q8_0, tail_value_decode,
      quant_kv_ggml_scale_f32, quant_kv_ggml_mad_f32, tail_execute, NULL};
  printf("QUANT_TAIL_CAP kind=%u heads=6 dim=128 capacity=256 prefixes=5,33 native_repeats=2 k_token_stride=%u v_token_stride=272 workspace=13120\n",
      attention_key_kind, 2 * row);
  const unsigned prefixes[] = {5, 33};
  for (unsigned prefix = 0; prefix < 2; ++prefix) {
    visible_tokens = prefixes[prefix];
    const float *golden = prefix ? attention_tail_gold_33 : attention_tail_gold_5;
    for (unsigned token = 0; token < 256; ++token) tail_mask[token] = token < visible_tokens ? 0 : UINT16_C(0xfc00);
    uintptr_t ordinary_flags = 0;
    for (unsigned trial = 0; trial < 3; ++trial) {
      const unsigned native = trial != 0;
      tail_trial = trial;
      memset(&output, 0xa5, sizeof(output)); memset(&context, 0, sizeof(context));
      printf("QUANT_TAIL_BEGIN visible=%u trial=%u native=%u\n", visible_tokens, trial, native);
      __asm__ volatile("vsetivli zero,1,e32,m1,ta,ma\nvmv.v.i v8,0\ncsrwi fcsr,0\ncsrwi vcsr,5"
                       : : : "v8", "memory");
      drain();
      int status, map = 0;
      akv_quant_strided_report_t report = {0};
      if (native) {
        akv_quant_selection_input_t input;
        map = akv_quant_ggml_map(&tail_dst, &mapping, &input);
        status = map ? AKV_QUANT_NATIVE_FALLBACK : akv_quant_strided_execute(
            &input, &bindings, tail_scratch, scratch_bytes, &report);
      } else {
        for (unsigned head = 0; head < HEADS; ++head)
          quantize_row_q8_0(attention_query + head * DIM, context.query[head], DIM);
        const akv_quant_online_plan_t plan = {HEADS, DIM, visible_tokens, attention_scale,
            &context, tail_qk, tail_value, quant_kv_ggml_scale_f32, quant_kv_ggml_mad_f32};
        status = akv_quant_online_head_major(&plan, &output.data[0][0], STRIDE, &workspace);
      }
      drain();
      uintptr_t fc, vc;
      __asm__ volatile("frcsr %0;csrr %1,vcsr" : "=r"(fc), "=r"(vc));
      if (!native) ordinary_flags = fc;
      const unsigned tiles = (visible_tokens + 31) / 32;
      const unsigned calls = native ? report.native.command_attempts : context.calls;
      const unsigned values = native ? report.native.value_decodes : context.values;
      unsigned errors = map || status || fc > 31 || fc != ordinary_flags || vc != 5;
      errors += calls != (native ? 2 * tiles : HEADS * visible_tokens);
      errors += values != (native ? visible_tokens : HEADS * visible_tokens);
      if (native)
        errors += report.native.selection_reason || report.native.completed_groups != 1 ||
            report.native.executor_status != QBS_STATUS_OK || report.key_panels != tiles || report.key_bytes != visible_tokens * row;
      for (unsigned head = 0; head < HEADS; ++head) {
        for (unsigned dim = 0; dim < DIM; ++dim) {
          const float actual = output.data[head][dim], expected = golden[head * DIM + dim];
          errors += !isfinite(actual) || !isfinite(expected) || fabsf(actual - expected) > 0.004f + 0.002f * fabsf(expected);
          if (trial == 1) previous_native[head][dim] = actual;
          if (trial == 2) errors += bits(actual) != bits(previous_native[head][dim]);
        }
        for (unsigned dim = DIM; dim < STRIDE; ++dim) errors += bits(output.data[head][dim]) != UINT32_C(0xa5a5a5a5);
      }
      for (unsigned i = 0; i < 64; ++i) errors += output.before[i] != 0xa5 || output.after[i] != 0xa5;
      printf("QUANT_TAIL_RESULT visible=%u trial=%u native=%u map=%d status=%d selection=%u groups=%u commands=%u calls=%u values=%u panels=%lu copied=%lu fcsr=%lu vcsr=%lu errors=%u hex=",
          visible_tokens, trial, native, map, status, report.native.selection_reason, report.native.completed_groups,
          report.native.command_attempts, calls, values, (unsigned long)report.key_panels,
          (unsigned long)report.key_bytes, (unsigned long)fc, (unsigned long)vc, errors);
      for (unsigned head = 0; head < HEADS; ++head)
        for (unsigned dim = 0; dim < DIM; ++dim) printf("%08x", bits(output.data[head][dim]));
      printf("\n");
      if (errors) return 1;
    }
  }
  printf("QUANT_TAIL_SUITE_PASS prefixes=2 trials=6 outputs=768 native_calls=4\n");
  return 0;
}
