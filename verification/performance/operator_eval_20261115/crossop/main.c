#include <stdint.h>
#include <string.h>
#include "qbs/qbs.h"
#include "config.h"
#include "plan_config.h"
#include "verify.h"
#include "printf.h"
#if EVAL_X32
#include "repack_kernels.h"
#endif

enum { M=EVAL_M,N=EVAL_N,K=2048,KB=8,AB=M*KB*292,IB=M*K*4,WB=N*KB*144,
       GUARD=64,TRIALS=2,MAX_COMMANDS=8 };
extern const float reuse_input[M*K],reuse_expected_gate[M*N],reuse_expected_up[M*N];
extern const unsigned char reuse_weights_gate[WB],reuse_weights_up[WB],reuse_expected_q8[AB],reuse_expected_packed[AB];
static const float *expected(unsigned t) { return t ? reuse_expected_up : reuse_expected_gate; }
static const unsigned char *weight(unsigned t) { return t ? reuse_weights_up : reuse_weights_gate; }
extern void quantize_row_q8_K(const float *,void *,int64_t);
static struct { unsigned char before[GUARD],data[AB],after[GUARD]; }
  q8 __attribute__((aligned(64))),packed __attribute__((aligned(64)));
static struct { unsigned char before[GUARD]; float data[M*N]; unsigned char after[GUARD]; }
  output __attribute__((aligned(64)));
static struct { unsigned char before[GUARD]; float data[M*K]; unsigned char after[GUARD]; }
  input __attribute__((aligned(64)));
static struct { unsigned char before[GUARD],data[WB],after[GUARD]; }
  weights __attribute__((aligned(64)));

typedef struct { uint64_t fcsr,vcsr,vstart; } csr_t;
typedef struct {
  uint64_t header,weight,activation,output;
  unsigned m,n,stride,segmented;
} command_t;
typedef struct {
  uint64_t t[6],caps5;
  csr_t before,quant,pack,after;
  unsigned status,eligible,context,coop,ctx_capacity,ctx_count,ctx_max_m,ctx_max_k;
  unsigned quant_calls,pack_ops,query_calls,plan_calls,execute_calls,planned,actual;
  command_t commands[MAX_COMMANDS];
} record_t;
typedef struct {
  reuse_check_t out,q8,pack,input,weight,guard,identity;
  unsigned work_n,work_bad,csr_bad;
} proof_t;

static inline uint64_t stamp(void) {
  uint64_t c; __asm__ volatile("rdcycle %0":"=r"(c)::"memory"); return c;
}
static inline csr_t csrs(void) {
  csr_t c;
  __asm__ volatile("csrr %0, fcsr\ncsrr %1, vcsr\ncsrr %2, vstart"
    :"=r"(c.fcsr),"=r"(c.vcsr),"=r"(c.vstart)::"memory");
  return c;
}

#if !EVAL_X32
__attribute__((noinline))
static qbs_status_t record_execute(void *context,const qbs_descriptor_t *d,unsigned m,
    const void *a,float *o,size_t stride,unsigned n,int segmented) {
  record_t *r=context;
  unsigned i=r->actual++;
  if (i<MAX_COMMANDS) r->commands[i]=(command_t){d->header,d->weight_base,
      (uintptr_t)a,(uintptr_t)o,m,n,(unsigned)stride,(unsigned)segmented};
  return qbs_native_execute_command(NULL,d,m,a,o,stride,n,segmented);
}
#endif

__attribute__((noinline,noclone))
static void reuse_trial(unsigned trial,record_t *r) {
  __asm__ volatile("csrr zero, cycle":::"memory");
  r->t[0]=stamp();
  if (!EVAL_SHARED || !trial) for (unsigned row=0;row<M;++row) {
    ++r->quant_calls;
    quantize_row_q8_K(input.data+row*K,q8.data+row*KB*292,K);
  }
  r->t[1]=stamp();
  r->quant=csrs();
  qbs_status_t status=QBS_STATUS_OK;
  if (EVAL_SHARED && trial) { /* Previously validated packed activation remains live. */ }
  else if (EVAL_TILE==8) {
    ++r->pack_ops;
    status=qbs_pack_activation_m8_grouped(1,q8.data,AB,M,KB,packed.data,AB);
  } else if (EVAL_TILE==4) {
    for (unsigned row=0;row<M && !status;row+=4) {
      ++r->pack_ops;
      status=qbs_pack_activation_m4(1,q8.data+row*KB*292,4*KB*292,KB,
                                  packed.data+row*KB*292,4*KB*292);
    }
  } else { ++r->pack_ops; memcpy(packed.data,q8.data,AB); }
  r->t[2]=stamp();
  r->pack=csrs();
#if !EVAL_X32
  qbs_device_t device;
  qbs_plan_t plan;
  qbs_profile_binding_t binding;
  qbs_execution_options_t options={0};
  const qbs_problem_t problem={.weight_profile=1,.activation_profile=1,.weight_layout=2,
    .activation_storage=EVAL_STORAGE,.m=M,.n=N,.k_elements=K};
  if (!status) { ++r->query_calls; status=qbs_device_query(qbs_native_info,NULL,&device); }
  if (!status) {
    r->caps5=qbs_native_info(NULL,QBS_COOPERATIVE_CAPABILITY_INDEX);
    r->coop=device.capabilities.q4_k_cooperative;
    r->ctx_capacity=device.capabilities.activation_context_capacity_bytes;
    r->ctx_count=device.capabilities.activation_context_count;
    r->ctx_max_m=device.capabilities.activation_context_max_m;
    r->ctx_max_k=device.capabilities.activation_context_max_k_blocks;
    if (r->coop!=(r->caps5&1u)) status=QBS_STATUS_CAPABILITY;
  }
  if (!status) status=qbs_device_bind_encodings(&device,QBS_WEIGHT_ENCODING_Q4_K,
                                              QBS_ACTIVATION_ENCODING_Q8_K,&binding);
  if (!status) { ++r->plan_calls; status=qbs_plan_create(&device,&problem,&plan); }
  if (!status) {
    r->eligible=!!qbs_plan_supports_activation_context(&plan);
    if (plan.split_k || plan.workspace_bytes || plan.needs_activation_gather || plan.k_blocks!=KB)
      status=QBS_STATUS_SHAPE;
    if (EVAL_REUSE && !r->eligible) status=QBS_STATUS_CONTEXT_UNSUPPORTED;
    qbs_plan_cursor_t cursor;
    qbs_plan_cursor_reset(&cursor);
    while (!status) {
      qbs_command_t c; int has;
      status=qbs_plan_next(&plan,&cursor,&c,&has);
      if (status || !has) break;
      ++r->planned;
    }
    options.use_activation_context=!!EVAL_REUSE;
    options.activation_context.context_id=0;
    options.activation_context.generation=EVAL_REUSE==2 ? 1 : trial+1;
    options.activation_context_scope=EVAL_REUSE==2
      ? (trial ? QBS_ACTIVATION_CONTEXT_SCOPE_REUSE_RELEASE : QBS_ACTIVATION_CONTEXT_SCOPE_FILL_KEEP)
      : QBS_ACTIVATION_CONTEXT_SCOPE_OPERATION;
    r->context=options.use_activation_context;
  }
#endif
  r->t[3]=stamp();
  __asm__ volatile("csrw fflags, %0"::"r"((uint64_t)(trial ? 8 : 0)):"memory");
  if (!status) {
    ++r->execute_calls;
#if EVAL_X32
    for (unsigned col=0;col<N;col+=32) {
      const block_q4_Kx32_ara *w=(const void *)(weights.data+col*KB*144);
      if (M==1) {
        ++r->actual;
        q4k_gemv_32(w,(const void *)q8.data,output.data+col,K);
      } else for (unsigned row=0;row<M;row+=4) {
        ++r->actual;
        q4k_gemm_32x4(w,(const void *)(packed.data+row*KB*292),
                     output.data+(col/32*M+row)*32,K);
      }
    }
#else
    status=qbs_execute_with_options(&plan,weights.data,WB,packed.data,AB,output.data,
        M*N,N,NULL,0,&options,record_execute,r);
#endif
  }
  r->t[4]=stamp();
  __asm__ volatile("fence rw, rw":::"memory");
  r->t[5]=stamp();
  r->after=csrs();
  __asm__ volatile("csrr zero, cycle":::"memory");
  r->status=status;
}

static void merge(reuse_check_t *a,reuse_check_t b) {
  if (!a->errors && b.errors) a->first_bad=a->checked+b.first_bad;
  a->checked+=b.checked; a->errors+=b.errors;
}

__attribute__((noinline))
static proof_t validate(unsigned trial,const record_t *r,reuse_check_t identity) {
  proof_t p={0};
  p.identity=identity;
  p.out=reuse_check_output(output.data,expected(trial),M,N,EVAL_X32,!EVAL_X32);
  p.q8=reuse_check_bytes(q8.data,reuse_expected_q8,AB);
  p.pack=reuse_check_bytes(packed.data,reuse_expected_packed,AB);
  p.input=reuse_check_bytes(input.data,reuse_input,IB);
  p.weight=reuse_check_bytes(weights.data,weight(trial),WB);
  p.guard=reuse_check_init();
  const void *g[]={q8.before,q8.after,packed.before,packed.after,output.before,output.after,
                   input.before,input.after,weights.before,weights.after};
  for (unsigned i=0;i<10;++i) merge(&p.guard,reuse_check_guard(g[i],GUARD));
  const unsigned seed=trial ? 8 : 0;
  p.csr_bad=!!(r->before.fcsr || r->before.vcsr!=(EVAL_SHARED && trial ? 2u : 0u) || r->before.vstart ||
      (r->quant.fcsr&~3u) || r->quant.vcsr!=2 || r->quant.vstart ||
      r->pack.fcsr!=r->quant.fcsr || r->pack.vcsr!=r->quant.vcsr || r->pack.vstart ||
      r->after.vcsr!=r->quant.vcsr || r->after.vstart ||
      (EVAL_X32 ? ((r->after.fcsr&~1u)!=seed) : (r->after.fcsr!=((trial ? EVAL_UP_FLAGS : EVAL_GATE_FLAGS)|seed))));
#if EVAL_X32
  p.work_n=r->actual;
  p.work_bad=!!(r->actual!=(N/32)*(M==1 ? 1 : M/4) || r->planned || r->query_calls ||
                r->plan_calls || r->context || r->eligible || r->coop);
#else
  p.work_n=r->actual;
  p.work_bad=!!(r->planned!=EVAL_COMMANDS || r->actual!=EVAL_COMMANDS ||
      r->query_calls!=1 || r->plan_calls!=1 || r->context!=!!EVAL_REUSE ||
      r->eligible!=(M==1));
  for (unsigned i=0;i<r->actual && i<MAX_COMMANDS;++i) {
    const command_t *a=&r->commands[i];
    if (i>=EVAL_COMMANDS) { ++p.work_bad; continue; }
    const reuse_expected_command_t *e=&reuse_expected_commands[i];
    const unsigned access=EVAL_REUSE==0 ? 0 : (EVAL_REUSE==1
      ? (i==0 ? 1 : (i+1==EVAL_COMMANDS ? 3 : 2))
      : (trial==0 ? (i==0 ? 1 : 2) : (i+1==EVAL_COMMANDS ? 3 : 2)));
    qbs_descriptor_fields_t f={.descriptor_version=QBS_DESCRIPTOR_VERSION,.weight_profile=1,
      .activation_profile=1,.weight_layout=2,.activation_layout=e->layout,.n=e->n,.k_blocks=KB,
      .activation_access=access,.context_id=0,
      .context_generation=EVAL_REUSE ? (EVAL_REUSE==2 ? 1 : trial+1) : 0};
    p.work_bad+=!!(a->header!=qbs_pack_descriptor_header(&f) || a->m!=e->m || a->n!=e->n ||
      a->stride!=N || a->segmented || a->weight!=(uintptr_t)(weights.data+e->col*KB*144) ||
      a->activation!=(uintptr_t)(packed.data+e->row*KB*292) ||
      a->output!=(uintptr_t)(output.data+e->row*N+e->col));
  }
#endif
  p.work_bad+=!!(r->quant_calls!=(EVAL_SHARED && trial ? 0 : M) ||
      r->pack_ops!=(EVAL_SHARED && trial ? 0 : (EVAL_TILE==4 ? M/4 : 1)) || r->execute_calls!=1);
  return p;
}

int main(void) {
  record_t records[TRIALS]={0}; proof_t proofs[TRIALS]={0}; unsigned completed=0,errors=0;
  memcpy(input.data,reuse_input,IB);
  void *g[]={q8.before,q8.after,packed.before,packed.after,output.before,output.after,
             input.before,input.after,weights.before,weights.after};
  for (unsigned i=0;i<10;++i) memset(g[i],0xa5,GUARD);
  for (unsigned trial=0;trial<TRIALS;++trial) {
    reuse_check_t identity=reuse_check_bytes(input.data,reuse_input,IB);
    memcpy(weights.data,weight(trial),WB);
    merge(&identity,reuse_check_bytes(weights.data,weight(trial),WB));
    if (EVAL_SHARED && trial) {
      merge(&identity,reuse_check_bytes(q8.data,reuse_expected_q8,AB));
      merge(&identity,reuse_check_bytes(packed.data,reuse_expected_packed,AB));
    } else { memset(q8.data,0x5a,AB); memset(packed.data,0x5a,AB); }
    if (identity.errors) { errors+=identity.errors; break; }
    memset(output.data,0x5a,sizeof(output.data));
    __asm__ volatile("csrwi fcsr, 0\ncsrwi vstart, 0":::"memory");
    if (!EVAL_SHARED || !trial) __asm__ volatile("csrwi vcsr, 0":::"memory");
    records[trial].before=csrs();
    reuse_trial(trial,&records[trial]);
    proofs[trial]=validate(trial,&records[trial],identity);
    ++completed;
    proof_t *p=&proofs[trial];
    errors+=records[trial].status!=0 || p->out.errors || p->q8.errors || p->pack.errors ||
      p->input.errors || p->weight.errors || p->guard.errors || p->identity.errors || p->work_bad || p->csr_bad;
    if (errors) break;
  }
  printf("QBR_META id=%s m=%u n=%u k=2048 tile=%u rvv=%u reuse=%u shared=%u trials=2\n",
         EVAL_ID,M,N,EVAL_TILE,EVAL_X32,EVAL_REUSE,EVAL_SHARED);
  for (unsigned t=0;t<completed;++t) {
    const record_t *r=&records[t]; const proof_t *p=&proofs[t];
    printf("QBR_TIME trial=%u status=%u t0=%lu t1=%lu t2=%lu t3=%lu t4=%lu t5=%lu\n",
        t,r->status,r->t[0],r->t[1],r->t[2],r->t[3],r->t[4],r->t[5]);
    printf("QBR_CSR trial=%u before_f=%lu before_v=%lu before_s=%lu quant_f=%lu quant_v=%lu quant_s=%lu "
        "pack_f=%lu pack_v=%lu pack_s=%lu after_f=%lu after_v=%lu after_s=%lu\n",t,
        r->before.fcsr,r->before.vcsr,r->before.vstart,r->quant.fcsr,r->quant.vcsr,r->quant.vstart,
        r->pack.fcsr,r->pack.vcsr,r->pack.vstart,r->after.fcsr,r->after.vcsr,r->after.vstart);
    printf("QBR_WORK trial=%u quant=%u pack=%u query=%u plan=%u execute=%u planned=%u actual=%u "
        "eligible=%u context=%u coop=%u caps5=%lu ctx_bytes=%u ctx_count=%u ctx_m=%u ctx_k=%u\n",t,
        r->quant_calls,r->pack_ops,r->query_calls,r->plan_calls,r->execute_calls,r->planned,r->actual,
        r->eligible,r->context,r->coop,r->caps5,r->ctx_capacity,r->ctx_count,r->ctx_max_m,r->ctx_max_k);
    printf("QBR_PROOF trial=%u out_n=%u out_bad=%u q8_n=%u q8_bad=%u pack_n=%u pack_bad=%u "
        "input_n=%u input_bad=%u weight_n=%u weight_bad=%u guard_n=%u guard_bad=%u "
        "identity_n=%u identity_bad=%u work_n=%u work_bad=%u csr_bad=%u first_output_bad=%u\n",t,
        p->out.checked,p->out.errors,p->q8.checked,p->q8.errors,p->pack.checked,p->pack.errors,
        p->input.checked,p->input.errors,p->weight.checked,p->weight.errors,p->guard.checked,p->guard.errors,
        p->identity.checked,p->identity.errors,p->work_n,p->work_bad,p->csr_bad,p->out.first_bad);
  }
  printf("QBR_DONE errors=%u trials=%u\n",errors,completed);
  return errors!=0 || completed!=TRIALS;
}
