#include "native_prefix.h"
#include "printf.h"
#include "software/akv/experimental/quantized_kv/q8_0_value.h"

extern const float prefill_query[], prefill_golden[], prefill_scale;
extern const unsigned char prefill_key[], prefill_value[];
extern const unsigned prefill_q4;
extern void quantize_row_q8_0(const float *, void *, int64_t);
static void prefill_native_decode(const void *source,float *out,int64_t n) {
  akv_quant_q8_0_value(source,out,(size_t)n);
}
extern void quant_kv_ggml_mad_f32(int, float *, const float *, float);
extern void quant_kv_ggml_scale_f32(int, float *, float);

enum { ROWS = 8, DIM = 128, STRIDE = 136, FIRST_QUERY = 16 };
static akv_quant_native_workspace_t workspace;
static quant_prefill_native_context_t context;
static struct __attribute__((aligned(64))) {
  unsigned char before[64];
  float data[ROWS][STRIDE];
  unsigned char after[64];
} output;
static float baseline[ROWS][DIM];
static unsigned baseline_fcsr;
static const unsigned visible[ROWS] = {17,17,18,18,19,19,20,20};
typedef struct { quant_prefill_native_context_t *native; unsigned first; } row_pair_t;

static int pair_qk(void *opaque, unsigned first, unsigned rows, unsigned token,
    unsigned tokens, float *scores, size_t stride) {
  row_pair_t *p = opaque;
  if (first + rows > 2) return 1;
  return quant_prefill_native_qk(p->native, p->first + first, rows, token,
                               tokens, scores, stride);
}
static int pair_value(void *opaque, unsigned token, float *out, unsigned dim) {
  row_pair_t *p = opaque;
  return quant_prefill_native_value(p->native, token, out, dim);
}
static uint32_t bits(float f) { uint32_t b; memcpy(&b, &f, 4); return b; }
static uint64_t cycles(void) { uint64_t c; __asm__ volatile("rdcycle %0":"=r"(c)); return c; }
static void drain(void) { __asm__ volatile("vmv.x.s zero,v8\nfence rw,rw":::"memory"); }

int main(void) {
  qbs_device_t device;
  uintptr_t vlenb;
  __asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
  if (vlenb != 128 || qbs_device_query(qbs_native_info, NULL, &device) != QBS_STATUS_OK)
    return 1;
  qbs_profile_binding_t binding;
  if (qbs_device_bind_encodings(&device, prefill_q4 ? QBS_WEIGHT_ENCODING_Q4_0 :
        QBS_WEIGHT_ENCODING_Q8_0_WEIGHT, QBS_ACTIVATION_ENCODING_Q8_0, &binding) != QBS_STATUS_OK)
    return 1;
  const unsigned key_bytes = prefill_q4 ? 72 : 136;
  akv_quant_selection_input_t input = {0};
  input.key.data = prefill_key; input.key.token_stride = key_bytes;
  input.key.head_stride = key_bytes * 256;
  input.value.data = prefill_value; input.value.token_stride = 136;
  input.value.head_stride = 136 * 256;
  const akv_quant_selection_t selection = {
    .group_heads=ROWS, .kv_heads=1, .dim=DIM, .visible_tokens=20,
    .key_profile=prefill_q4 ? QBS_WEIGHT_PROFILE_Q4_0 : QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
    .key_row_bytes=key_bytes, .query_quant_row_bytes=136};
  const akv_quant_native_bindings_t bindings = {quantize_row_q8_0, prefill_native_decode,
    quant_kv_ggml_scale_f32, quant_kv_ggml_mad_f32, qbs_native_execute_command, NULL};
  printf("PREFILL_CAP q4=%u rows=8 d=128 first_query=16 tokens=20 trials=4\n", prefill_q4);
  const unsigned order[] = {0,1,1,0};
  for (unsigned trial=0; trial<4; ++trial) {
    const unsigned shared = order[trial];
    memset(&output, 0xa5, sizeof(output)); memset(&context, 0, sizeof(context));
    akv_quant_native_report_t report = {0};
    context.core = (akv_quant_native_context_t){&input, &bindings, &selection, &workspace, &report, 0};
    context.visible = visible;
    printf("PREFILL_BEGIN trial=%u shared=%u\n", trial, shared);
    /* The first drain is itself an RVV instruction: reset starts with vill. */
    __asm__ volatile("vsetivli zero,1,e32,m1,ta,ma\nvmv.v.i v8,0\ncsrwi fcsr,0\ncsrwi vcsr,5"
                     :::"memory","v8");
    drain();
    uint64_t start = cycles();
    for (unsigned row=0; row<ROWS; ++row) {
      unsigned query = FIRST_QUERY + row/2, head = row%2;
      quantize_row_q8_0(prefill_query + (head*20 + query)*DIM,
                       workspace.query + row*136, DIM);
    }
    int status = AKV_QUANT_OK;
    if (shared) {
      akv_quant_online_plan_t plan = {ROWS,DIM,20,prefill_scale,&context,
        quant_prefill_native_qk,quant_prefill_native_value,bindings.scale,bindings.mad};
      status = quant_prefill_prefix_schedule(&plan,visible,output.data[0],STRIDE,&workspace.online);
    } else {
      for (unsigned row=0; row<ROWS && !status; row+=2) {
        row_pair_t pair = {&context,row};
        akv_quant_online_plan_t plan = {2,DIM,visible[row],prefill_scale,&pair,
          pair_qk,pair_value,bindings.scale,bindings.mad};
        status = akv_quant_online_shared(&plan,output.data[row],STRIDE,&workspace.online);
      }
    }
    drain();
    uint64_t elapsed = cycles()-start;
    uintptr_t fc,vc; __asm__ volatile("frcsr %0;csrr %1,vcsr":"=r"(fc),"=r"(vc));
    unsigned errors = status != AKV_QUANT_OK || fc > 31 || vc != 5 ||
      report.command_attempts != 4 || report.value_decodes != (shared ? 20 : 74) ||
      context.alignment_copies != 0;
    if (!trial) baseline_fcsr=fc; else errors += fc!=baseline_fcsr;
    for (unsigned row=0; row<ROWS; ++row) {
      for (unsigned d=0; d<DIM; ++d) {
        float y=output.data[row][d];
        float gold=prefill_golden[((FIRST_QUERY+row/2)*16+row%2)*DIM+d];
        errors += !isfinite(y) || !isfinite(gold) || fabsf(y-gold)>2e-5f+2e-5f*fabsf(gold);
        if (!trial) baseline[row][d]=y; else errors += bits(y)!=bits(baseline[row][d]);
      }
      for (unsigned d=DIM; d<STRIDE; ++d) errors += bits(output.data[row][d])!=0xa5a5a5a5u;
    }
    for(unsigned i=0;i<64;++i) errors += output.before[i]!=0xa5 || output.after[i]!=0xa5;
    printf("PREFILL_RESULT trial=%u shared=%u cycles=%lu commands=%u values=%u fcsr=%lu vcsr=%lu errors=%u hex=",
      trial,shared,(unsigned long)elapsed,report.command_attempts,report.value_decodes,
      (unsigned long)fc,(unsigned long)vc,errors);
    for(unsigned row=0;row<ROWS;++row) for(unsigned d=0;d<DIM;++d) printf("%08x",bits(output.data[row][d]));
    printf("\n");
    if(errors) return 1;
  }
  printf("PREFILL_SUITE_PASS\n");
  return 0;
}
