#include <stdint.h>
#include <string.h>
#include "qbs/qbs.h"
#include "config.h"
#include "printf.h"
#include "compare.h"
#if EVAL_RVV
#include "repack_kernels.h"
#endif

enum { M=EVAL_M,N=EVAL_N,K=EVAL_K,KB=K/EVAL_BE,AB=M*KB*EVAL_AB,
       WB=N*KB*EVAL_WB,GUARD=64,TRIALS=2 };
extern const float eval_input[M*K], eval_expected[M*N];
extern const unsigned char eval_weights[WB],eval_q8[AB],eval_packed[AB];
extern void EVAL_QUANT(const float *,void *,int64_t);
#if EVAL_CANDIDATE
extern void EVAL_X32(const void *,const void *,float *,unsigned);
#endif
static struct { unsigned char before[GUARD],data[AB],after[GUARD]; }
  q8 __attribute__((aligned(64))),packed __attribute__((aligned(64)));
static struct { unsigned char before[GUARD]; float data[M*N]; unsigned char after[GUARD]; }
  output __attribute__((aligned(64)));
static struct { unsigned char before[GUARD]; float data[M*K]; unsigned char after[GUARD]; }
  input __attribute__((aligned(64)));
extern struct { unsigned char before[GUARD],data[WB],after[GUARD]; }
  weights __attribute__((aligned(64)));
static const unsigned char guard_golden[10*GUARD]={[0 ... 10*GUARD-1]=0xa5};
typedef struct {
  uint64_t t[6],quant_fcsr,quant_vcsr,fcsr,vcsr,vstart;
  unsigned status,commands;
  format_comparison checks[4];
} record_t;
static inline uint64_t stamp(void) {
  uint64_t c; __asm__ volatile("rdcycle %0":"=r"(c)::"memory"); return c;
}

__attribute__((noinline,noclone))
static void projection_trial(unsigned trial, record_t *r) {
  __asm__ volatile("csrr zero, cycle":::"memory");
  r->t[0]=stamp();
  for (unsigned row=0;row<M;++row) EVAL_QUANT(input.data+row*K,q8.data+row*KB*EVAL_AB,K);
  r->t[1]=stamp();
  __asm__ volatile("csrr %0, fcsr\ncsrr %1, vcsr":"=r"(r->quant_fcsr),"=r"(r->quant_vcsr)::"memory");
  qbs_status_t status=QBS_STATUS_OK;
  if (M==4 && (!EVAL_RVV || EVAL_PROFILE==1))
    status=qbs_pack_activation_m4(EVAL_AP,q8.data,AB,KB,packed.data,AB);
  r->t[2]=stamp();
#if !EVAL_RVV
  qbs_device_t device; qbs_plan_t plan; qbs_profile_binding_t binding;
  qbs_problem_t p={.weight_profile=EVAL_PROFILE,.activation_profile=EVAL_AP,.weight_layout=2,
    .activation_storage=M==4 ? 2 : 1,.m=M,.n=N,.k_elements=K};
  if (!status) status=qbs_device_query(qbs_native_info,NULL,&device);
  if (!status) status=qbs_device_bind_encodings(&device,qbs_weight_encoding_id(EVAL_PROFILE),
    qbs_activation_encoding_id(EVAL_AP),&binding);
  if (!status) status=qbs_plan_create(&device,&p,&plan);
  if (!status) {
    if (plan.split_k || plan.workspace_bytes || plan.needs_activation_gather || plan.k_blocks!=KB)
      status=QBS_STATUS_SHAPE;
    qbs_plan_cursor_t cursor; qbs_plan_cursor_reset(&cursor);
    for (int has=1;has && !status;) {
      qbs_command_t c; status=qbs_plan_next(&plan,&cursor,&c,&has); r->commands+=!!has;
    }
  }
#endif
  r->t[3]=stamp();
  __asm__ volatile("csrw fflags, %0"::"r"((uint64_t)(trial ? 8 : 0)):"memory");
  if (!status) {
#if EVAL_RVV
#if EVAL_M == 4 && EVAL_PROFILE == 1
    for (unsigned col=0;col<N;col+=32) {
      float tile[4*32];
      q4k_gemm_32x4((const void *)(weights.data+col*KB*EVAL_WB),
                    (const void *)packed.data,tile,K);
      for (unsigned row=0;row<4;++row)
        memcpy(output.data+row*N+col,tile+row*32,32*sizeof(float));
    }
#elif EVAL_M == 4 && EVAL_PROFILE == 2
    for (unsigned col=0;col<N;col+=32)
      q6k_gemm_32x4((const void *)(weights.data+col*KB*EVAL_WB),
                    (const void *)q8.data,KB,output.data+col,N,K);
#else
    for (unsigned row=0;row<M;++row) for (unsigned col=0;col<N;col+=32)
      EVAL_X32((const void *)(weights.data+col*KB*EVAL_WB),
               (const void *)(q8.data+row*KB*EVAL_AB),output.data+row*N+col,K);
#endif
#else
    qbs_execution_options_t options={0};
    status=qbs_execute_with_options(&plan,weights.data,WB,M==1 ? q8.data : packed.data,AB,
      output.data,M*N,N,NULL,0,&options,qbs_native_execute_command,NULL);
#endif
  }
  r->t[4]=stamp();
  __asm__ volatile("fence rw, rw":::"memory");
  r->t[5]=stamp();
  __asm__ volatile("csrr %0, fcsr\ncsrr %1, vcsr\ncsrr %2, vstart"
    :"=r"(r->fcsr),"=r"(r->vcsr),"=r"(r->vstart)::"memory");
  __asm__ volatile("csrr zero, cycle":::"memory");
  r->status=status;
}

static void diagnostic(unsigned trial, const char *kind, format_comparison c,
                       const void *actual, unsigned bytes) {
  if (!c.mismatches && !EVAL_DIAGNOSTIC) return;
  const unsigned char *p=actual;
  unsigned first=c.mismatches ? c.first*(kind[0]=='O' ? 4u : 1u) : 0;
  printf("OPR_RAW trial=%u kind=%s offset=%u hex=",trial,kind,first);
  for (unsigned i=first;i<bytes && i<first+16;++i) printf("%02x",(unsigned)p[i]);
  printf("\n");
}

int main(void) {
  record_t records[TRIALS]={0}; unsigned errors=0;
  const char *names[]={"Q8","PACK","OUT","GUARD"};
  memcpy(input.data,eval_input,sizeof(input.data));
  for (unsigned t=0;t<TRIALS;++t) {
    unsigned char *g[]={q8.before,q8.after,packed.before,packed.after,output.before,
      output.after,input.before,input.after,weights.before,weights.after};
    for (unsigned j=0;j<10;++j) memset(g[j],0xa5,GUARD);
    memset(q8.data,0x5a,AB); memset(packed.data,0x5a,AB); memset(output.data,0x5a,sizeof(output.data));
    __asm__ volatile("csrwi fcsr, 0\ncsrwi vcsr, 0\ncsrwi vstart, 0":::"memory");
    projection_trial(t,&records[t]);
    unsigned char guard_raw[10*GUARD];
    for (unsigned j=0;j<10;++j) memcpy(guard_raw+j*GUARD,g[j],GUARD);
    const void *actual[]={q8.data,
      M==4 && (!EVAL_RVV || EVAL_PROFILE==1) ? packed.data : q8.data,output.data,guard_raw};
    const void *expected[]={eval_q8,eval_packed,eval_expected,guard_golden};
    unsigned count[]={AB,AB,M*N,10*GUARD};
    errors+=records[t].status!=0;
    for (unsigned j=0;j<4;++j) {
      format_comparison c=format_compare(actual[j],expected[j],count[j],j==2,
        EVAL_RVV && j==2,0.0002f,0.0002f);
      records[t].checks[j]=c; errors+=c.mismatches!=0;
      diagnostic(t,names[j],c,actual[j],count[j]*(j==2 ? 4 : 1));
    }
  }
  printf("OPR_META id=%s m=%u n=%u k=%u profile=%u ap=%u kb=%u ab=%u rvv=%u trials=2 policy=1\n",
    EVAL_ID,M,N,K,EVAL_PROFILE,EVAL_AP,KB,EVAL_AB,EVAL_RVV);
  for (unsigned t=0;t<TRIALS;++t) {
    record_t *r=&records[t];
    printf("OPR_TRIAL trial=%u status=%u commands=%u t0=%lu t1=%lu t2=%lu t3=%lu t4=%lu t5=%lu "
      "quant_fcsr=%lu quant_vcsr=%lu fcsr=%lu vcsr=%lu vstart=%lu\n",t,r->status,r->commands,
      r->t[0],r->t[1],r->t[2],r->t[3],r->t[4],r->t[5],r->quant_fcsr,r->quant_vcsr,r->fcsr,r->vcsr,r->vstart);
    for (unsigned j=0;j<4;++j) {
      format_comparison *c=&r->checks[j];
      printf("OPR_CHECK trial=%u kind=%s count=%u mismatches=%u first=%u expected_hash=%u actual_hash=%u "
        "raw_differences=%u first_actual=%u first_expected=%u\n",t,names[j],c->count,c->mismatches,c->first,
        c->expected_hash,c->actual_hash,c->raw_differences,c->first_actual,c->first_expected);
    }
  }
  printf("OPR_DONE errors=%u\n",errors);
  return errors!=0;
}
