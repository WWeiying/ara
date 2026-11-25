#include <stdint.h>
#include <string.h>
#include "qbs/qbs.h"
#include "config.h"
#include "printf.h"
#if EVAL_X32
#include "repack_kernels.h"
#endif

enum { M=EVAL_M, N=EVAL_N, K=2048, KB=8, AB=M*KB*292,
       WB=N*KB*EVAL_WB, GUARD=64, TRIALS=2 };
extern const float eval_input[M*K];
extern const unsigned char eval_weights[WB], eval_row_weights[WB], eval_x32_weights[WB];
extern void quantize_row_q8_K(const float *, void *, int64_t);
extern void EVAL_DOT(int, float *, size_t, const void *, size_t, const void *, size_t, int);
static struct { unsigned char before[GUARD], data[AB], after[GUARD]; }
  q8 __attribute__((aligned(64))), packed __attribute__((aligned(64)));
static struct { unsigned char before[GUARD]; float data[M*N]; unsigned char after[GUARD]; }
  output __attribute__((aligned(64)));
static struct { unsigned char before[GUARD]; float data[M*K]; unsigned char after[GUARD]; }
  input __attribute__((aligned(64)));
static struct { unsigned char before[GUARD], data[WB], after[GUARD]; }
  weights __attribute__((aligned(64)));
static unsigned char q8_snap[TRIALS][AB], packed_snap[TRIALS][AB], guards[TRIALS][10][GUARD];
static float out_snap[TRIALS][M*N];
typedef struct { uint64_t t[6], quant_fcsr, fcsr, vcsr, vstart;
  unsigned status, commands, context, eligible, coop; } record_t;
static inline uint64_t stamp(void) {
  uint64_t c; __asm__ volatile("rdcycle %0" : "=r"(c) : : "memory"); return c;
}

__attribute__((noinline, noclone))
static void eval_trial(unsigned trial, record_t *r) {
  __asm__ volatile("csrr zero, cycle" : : : "memory");
  r->t[0] = stamp();
  for (unsigned row = 0; row < M; ++row)
    quantize_row_q8_K(input.data+row*K, q8.data+row*KB*292, K);
  r->t[1] = stamp();
  __asm__ volatile("csrr %0, fcsr" : "=r"(r->quant_fcsr) : : "memory");
  qbs_status_t status = QBS_STATUS_OK;
  if ((!EVAL_RVV || EVAL_X32) && EVAL_TILE == 8)
    status = qbs_pack_activation_m8_grouped(1, q8.data, AB, M, KB, packed.data, AB);
  else if ((!EVAL_RVV || EVAL_X32) && EVAL_TILE == 4)
    for (unsigned row = 0; row < M && status == QBS_STATUS_OK; row += 4)
      status = qbs_pack_activation_m4(1, q8.data+row*KB*292, 4*KB*292, KB,
                                    packed.data+row*KB*292, 4*KB*292);
  else memcpy(packed.data, q8.data, AB);
  r->t[2] = stamp();
  qbs_device_t device;
  qbs_plan_t plan;
  qbs_execution_options_t options = {0};
  if (!EVAL_RVV) {
    const qbs_problem_t p = {.weight_profile=EVAL_PROFILE, .activation_profile=1,
      .weight_layout=2, .activation_storage=EVAL_STORAGE, .m=M, .n=N, .k_elements=K};
    qbs_profile_binding_t binding;
    if (!status) status = qbs_device_query(qbs_native_info, NULL, &device);
    if (!status) status = qbs_device_bind_encodings(&device,
        qbs_weight_encoding_id(EVAL_PROFILE), QBS_ACTIVATION_ENCODING_Q8_K, &binding);
    if (!status) status = qbs_plan_create(&device, &p, &plan);
    if (!status) {
      r->eligible = !!qbs_plan_supports_activation_context(&plan);
      r->coop = device.capabilities.q4_k_cooperative;
      if (plan.split_k || plan.workspace_bytes || plan.needs_activation_gather || plan.k_blocks != KB)
        status = QBS_STATUS_SHAPE;
      qbs_plan_cursor_t cursor;
      qbs_plan_cursor_reset(&cursor);
      for (int has = 1; has && !status;) {
        qbs_command_t c;
        status = qbs_plan_next(&plan, &cursor, &c, &has);
        r->commands += !!has;
      }
      options.use_activation_context = EVAL_REUSE && r->eligible;
      options.activation_context.context_id = 0;
      options.activation_context.generation = EVAL_REUSE == 2 ? 1 : trial+1;
      options.activation_context_scope = EVAL_REUSE == 2
        ? (trial ? QBS_ACTIVATION_CONTEXT_SCOPE_REUSE_RELEASE : QBS_ACTIVATION_CONTEXT_SCOPE_FILL_KEEP)
        : QBS_ACTIVATION_CONTEXT_SCOPE_OPERATION;
      r->context = options.use_activation_context;
    }
  }
  r->t[3] = stamp();
  __asm__ volatile("csrw fflags, %0" : : "r"((uint64_t)(trial ? 8 : 0)) : "memory");
  if (!status) {
    if (EVAL_RVV) {
#if EVAL_X32
      for (unsigned col = 0; col < N; col += 32) {
#if EVAL_PROFILE == 1
        const block_q4_Kx32_ara *w = (const void *)(weights.data+col*KB*EVAL_WB);
        if (M == 1) q4k_gemv_32(w, (const void *)q8.data, output.data+col, K);
        else for (unsigned row = 0; row < M; row += 4)
          q4k_gemm_32x4(w, (const void *)(packed.data+row*KB*292),
                       output.data+(col/32*M+row)*32, K);
#else
        const block_q6_Kx32_ara *w = (const void *)(weights.data+col*KB*EVAL_WB);
        q6k_gemv_32(w, (const void *)q8.data, output.data+col, K);
#endif
      }
#else
      for (unsigned row = 0; row < M; ++row)
        for (unsigned col = 0; col < N; ++col)
          EVAL_DOT(K, output.data+row*N+col, 0, weights.data+col*KB*EVAL_WB, 0,
                   q8.data+row*KB*292, 0, 1);
#endif
    } else status = qbs_execute_with_options(&plan, weights.data, WB, packed.data, AB,
        output.data, M*N, N, NULL, 0, &options, qbs_native_execute_command, NULL);
  }
  r->t[4] = stamp();
  __asm__ volatile("fence rw, rw" : : : "memory");
  r->t[5] = stamp();
  __asm__ volatile("csrr %0, fcsr\ncsrr %1, vcsr\ncsrr %2, vstart"
    : "=r"(r->fcsr), "=r"(r->vcsr), "=r"(r->vstart) : : "memory");
  __asm__ volatile("csrr zero, cycle" : : : "memory");
  r->status = status;
}
static unsigned bits(float f) { unsigned u; memcpy(&u, &f, 4); return u; }
static void hex(const unsigned char *p, unsigned n) {
  for (unsigned i=0; i<n; ++i) printf("%02x", (unsigned)p[i]);
  printf("\n");
}
int main(void) {
  record_t records[TRIALS] = {0};
  memcpy(input.data, eval_input, sizeof(input.data));
  memcpy(weights.data, EVAL_X32 ? eval_x32_weights : (EVAL_RVV ? eval_row_weights : eval_weights), WB);
  unsigned errors = 0;
  for (unsigned t=0; t<TRIALS; ++t) {
    unsigned char *g[] = {q8.before,q8.after,packed.before,packed.after,output.before,
      output.after,input.before,input.after,weights.before,weights.after};
    for (unsigned j=0; j<10; ++j) memset(g[j], 0xa5, GUARD);
    memset(q8.data, 0x5a, AB); memset(packed.data, 0x5a, AB);
    memset(output.data, 0x5a, sizeof(output.data));
    __asm__ volatile("csrwi fcsr, 0\ncsrwi vcsr, 0\ncsrwi vstart, 0" : : : "memory");
    eval_trial(t, &records[t]);
    errors += records[t].status != 0;
    memcpy(q8_snap[t], q8.data, AB); memcpy(packed_snap[t], packed.data, AB);
    if (EVAL_X32 && EVAL_PROFILE == 1)
      for (unsigned row=0; row<M; ++row)
        for (unsigned col=0; col<N; ++col)
          out_snap[t][row*N+col] = output.data[(col/32*M+row)*32+col%32];
    else memcpy(out_snap[t], output.data, sizeof(output.data));
    for (unsigned j=0; j<10; ++j) memcpy(guards[t][j], g[j], GUARD);
  }
  printf("OPQ_META id=%s m=%u n=%u k=2048 profile=%u rvv=%u trials=2\n",
         EVAL_ID, M, N, EVAL_PROFILE, EVAL_RVV);
  for (unsigned t=0; t<TRIALS; ++t) {
    record_t *r=&records[t];
    printf("OPQ_TRIAL trial=%u status=%u commands=%u context=%u eligible=%u coop=%u "
      "t0=%lu t1=%lu t2=%lu t3=%lu t4=%lu t5=%lu quant_fcsr=%lu fcsr=%lu vcsr=%lu vstart=%lu\n",
      t,r->status,r->commands,r->context,r->eligible,r->coop,
      r->t[0],r->t[1],r->t[2],r->t[3],r->t[4],r->t[5],r->quant_fcsr,r->fcsr,r->vcsr,r->vstart);
    for (unsigned j=0; j<10; ++j) {
      printf("OPQ_GUARD trial=%u index=%u hex=",t,j); hex(guards[t][j],GUARD);
    }
    for (unsigned j=0; j<M*KB; ++j) {
      printf("OPQ_Q8 trial=%u block=%u hex=",t,j); hex(q8_snap[t]+j*292,292);
      printf("OPQ_PACK trial=%u block=%u hex=",t,j); hex(packed_snap[t]+j*292,292);
    }
    for (unsigned i=0; i<M*N; ++i)
      printf("OPQ_OUT trial=%u index=%u bits=%08x\n",t,i,bits(out_snap[t][i]));
  }
  printf("OPQ_DONE errors=%u\n",errors);
  return errors != 0;
}
