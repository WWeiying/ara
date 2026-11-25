#include <stdint.h>
#include <string.h>
#include "qbs/qbs.h"
#include "config.h"
#include "plan_config.h"
#include "verify.h"
#include "printf.h"
enum { M=E_M,N=35,K=2048,KB=8,S=38,AB=M*8*292,IB=M*8192,WB=36*8*144,
       WS=E_WS ? E_WS : 4,GUARD=64,MAXC=6,TRIALS=2 };
extern const float boundary_input[M*K],boundary_expected[M*S];
extern const unsigned char boundary_weights[WB],boundary_q8[AB],boundary_ws[WS],boundary_acts[E_SNAP];
static struct { unsigned char before[64],data[AB],after[64]; }
  q8 __attribute__((aligned(64))),activation __attribute__((aligned(64)));
static struct { unsigned char before[64]; float data[M*S]; unsigned char after[64]; }
  output __attribute__((aligned(64)));
static struct { unsigned char before[64]; float data[M*K]; unsigned char after[64]; }
  input __attribute__((aligned(64)));
static struct { unsigned char before[64],data[WB],after[64]; } weights __attribute__((aligned(64)));
static struct { unsigned char before[64],data[WS],after[64]; } workspace __attribute__((aligned(64)));
extern void quantize_row_q8_K(const float *,void *,int64_t);
typedef struct { uint64_t f,v,s; } csr_t;
typedef struct { uint64_t header,weight,act,out; unsigned m,n,stride,split; } record_command_t;
typedef struct {
  uint64_t t[6]; csr_t before,quant,pack,after;
  qbs_device_t device; qbs_plan_t plan;
  unsigned status,actual,snapbytes,overrun,fallback,planned,eligible;
  record_command_t commands[MAXC]; unsigned char snapshots[E_SNAP];
} record_t;
typedef struct { reuse_check_t out,q8,act,input,weight,ws,snaps,guards; unsigned work_bad,csr_bad; } proof_t;
typedef struct { unsigned context,short_weight,short_ws,ws_tested,bad_k,bad_segment,calls;
  unsigned bytes,bad,csr_bad; csr_t after; } rejects_t;
static inline uint64_t stamp(void) { uint64_t c; __asm__ volatile("rdcycle %0":"=r"(c)::"memory"); return c; }
static inline csr_t csrs(void) {
  csr_t c; __asm__ volatile("csrr %0, fcsr\ncsrr %1, vcsr\ncsrr %2, vstart"
      :"=r"(c.f),"=r"(c.v),"=r"(c.s)::"memory"); return c;
}
__attribute__((noinline,noclone))
static qbs_status_t record_execute(void *p,const qbs_descriptor_t *d,unsigned m,const void *a,
    float *out,size_t stride,unsigned n,int split) {
  record_t *r=p; unsigned i=r->actual++;
  qbs_descriptor_fields_t f=qbs_unpack_descriptor_header(d->header);
  unsigned bytes=m*f.k_blocks*292;
  if (i<MAXC && bytes<=E_SNAP-r->snapbytes) {
    r->commands[i]=(record_command_t){d->header,d->weight_base,(uintptr_t)a,(uintptr_t)out,m,n,(unsigned)stride,(unsigned)split};
    memcpy(r->snapshots+r->snapbytes,a,bytes); r->snapbytes+=bytes;
  } else ++r->overrun;
  return qbs_native_execute_command(NULL,d,m,a,out,stride,n,split);
}
__attribute__((noinline,noclone))
static void boundary_trial(unsigned trial,record_t *r) {
  __asm__ volatile("csrr zero, cycle":::"memory"); r->t[0]=stamp();
  for (unsigned row=0;row<M;++row) quantize_row_q8_K(input.data+row*K,q8.data+row*KB*292,K);
  r->t[1]=stamp(); r->quant=csrs();
  memcpy(activation.data,q8.data,AB);
  r->t[2]=stamp(); r->pack=csrs();
  qbs_status_t status=qbs_device_query(qbs_native_info,NULL,&r->device);
  const qbs_problem_t problem={.weight_profile=1,.activation_profile=1,.weight_layout=2,
    .activation_storage=1,.m=M,.n=N,.k_elements=K};
  qbs_profile_binding_t binding;
  if (!status) status=qbs_device_bind_encodings(&r->device,QBS_WEIGHT_ENCODING_Q4_K,
                                               QBS_ACTIVATION_ENCODING_Q8_K,&binding);
  if (!status) status=E_SEG ? qbs_plan_create_segmented_r4(&r->device,&problem,E_SEG,&r->plan)
                           : qbs_plan_create(&r->device,&problem,&r->plan);
  if (!status) {
    r->eligible=!!qbs_plan_supports_activation_context(&r->plan);
    if (r->eligible || r->plan.workspace_bytes!=E_WS || r->plan.split_k!=!!E_SEG ||
        r->plan.needs_activation_gather!=!!E_SEG) status=QBS_STATUS_SHAPE;
    qbs_plan_cursor_t cursor; qbs_plan_cursor_reset(&cursor);
    while (!status) {
      qbs_command_t c; int has; status=qbs_plan_next(&r->plan,&cursor,&c,&has);
      if (status || !has) break;
      ++r->planned;
    }
  }
  r->fallback=trial!=0; r->t[3]=stamp();
  __asm__ volatile("csrw fflags, %0"::"r"((uint64_t)(trial ? 8 : 0)):"memory");
  if (!status) {
    if (trial) status=qbs_execute(&r->plan,weights.data,WB,activation.data,AB,output.data,
        M*S,S,workspace.data,E_WS,record_execute,r);
    else {
      qbs_execution_options_t direct={0};
      status=qbs_execute_with_options(&r->plan,weights.data,WB,activation.data,AB,output.data,
          M*S,S,workspace.data,E_WS,&direct,record_execute,r);
    }
  }
  r->t[4]=stamp(); __asm__ volatile("fence rw, rw":::"memory"); r->t[5]=stamp();
  r->after=csrs(); __asm__ volatile("csrr zero, cycle":::"memory"); r->status=status;
}
static void merge(reuse_check_t *a,reuse_check_t b) {
  if (!a->errors && b.errors) a->first_bad=a->checked+b.first_bad;
  a->checked+=b.checked; a->errors+=b.errors;
}
__attribute__((noinline,noclone))
static proof_t validate(unsigned trial,const record_t *r) {
  proof_t p={0};
  p.out=reuse_check_output(output.data,boundary_expected,M,S,0,1);
  p.q8=reuse_check_bytes(q8.data,boundary_q8,AB); p.act=reuse_check_bytes(activation.data,boundary_q8,AB);
  p.input=reuse_check_bytes(input.data,boundary_input,IB);
  p.weight=reuse_check_bytes(weights.data,boundary_weights,WB);
  p.ws=reuse_check_bytes(workspace.data,boundary_ws,WS);
  p.snaps=reuse_check_bytes(r->snapshots,boundary_acts,E_SNAP); p.guards=reuse_check_init();
  const void *guards[]={q8.before,q8.after,activation.before,activation.after,input.before,input.after,
    weights.before,weights.after,output.before,output.after,workspace.before,workspace.after};
  for (unsigned i=0;i<12;++i) merge(&p.guards,reuse_check_guard(guards[i],64));
  p.work_bad=!!(r->planned!=E_COMMANDS || r->actual!=E_COMMANDS || r->snapbytes!=E_SNAP || r->overrun || r->eligible);
  for (unsigned i=0;i<r->actual && i<MAXC && i<E_COMMANDS;++i) {
    const boundary_command_t *c=&boundary_commands[i]; const record_command_t *a=&r->commands[i];
    qbs_descriptor_fields_t f={.descriptor_version=QBS_DESCRIPTOR_VERSION,.weight_profile=1,
      .activation_profile=1,.weight_layout=2,.activation_layout=1,.n=c->n,.k_blocks=c->kb};
    p.work_bad+=!!(a->header!=qbs_pack_descriptor_header(&f) || a->weight!=(uintptr_t)(weights.data+c->wo) ||
        a->m!=M || a->n!=c->n || a->stride!=(E_SEG ? c->n : S) || a->split!=!!E_SEG ||
        a->act!=(uintptr_t)(E_SEG ? workspace.data+M*32*4 : activation.data) ||
        a->out!=(uintptr_t)(E_SEG ? (void *)workspace.data : (void *)(output.data+c->col)));
  }
  p.csr_bad=!!(r->before.f || r->before.v || r->before.s || (r->quant.f&~3u) ||
    r->quant.v!=2 || r->quant.s || r->pack.f!=r->quant.f || r->pack.v!=2 || r->pack.s ||
    r->after.f!=(E_FLAGS|(trial ? 8u : 0u)) || r->after.v!=2 || r->after.s);
  return p;
}
static unsigned proof_errors(const proof_t *p) {
  return p->out.errors || p->q8.errors || p->act.errors || p->input.errors || p->weight.errors ||
      p->ws.errors || p->snaps.errors || p->guards.errors || p->work_bad || p->csr_bad;
}
static qbs_status_t reject_executor(void *p,const qbs_descriptor_t *d,unsigned m,const void *a,
    float *o,size_t stride,unsigned n,int split) {
  (void)d;(void)m;(void)a;(void)o;(void)stride;(void)n;(void)split;
  ++*(unsigned *)p; return QBS_STATUS_EXECUTION;
}
__attribute__((noinline,noclone))
static rejects_t rejection_contract(const record_t *first) {
  rejects_t r={0}; qbs_plan_t bad; qbs_problem_t problem=first->plan.problem;
  qbs_execution_options_t context={.use_activation_context=1,.activation_context={0,1}};
  __asm__ volatile("csrwi fcsr, 8\ncsrwi vcsr, 2\ncsrwi vstart, 0":::"memory");
  r.context=qbs_execute_with_options(&first->plan,weights.data,WB,activation.data,AB,output.data,
      M*S,S,workspace.data,E_WS,&context,reject_executor,&r.calls);
  r.short_weight=qbs_execute(&first->plan,weights.data,WB-1,activation.data,AB,output.data,
      M*S,S,workspace.data,E_WS,reject_executor,&r.calls);
  if (E_WS) {
    r.ws_tested=1;
    r.short_ws=qbs_execute(&first->plan,weights.data,WB,activation.data,AB,output.data,
        M*S,S,workspace.data,E_WS-1,reject_executor,&r.calls);
  }
  problem.k_elements=2047; r.bad_k=qbs_plan_create(&first->device,&problem,&bad);
  problem.k_elements=2048;
  r.bad_segment=qbs_plan_create_segmented_r4(&first->device,&problem,
      first->device.capabilities.max_k_blocks+1,&bad);
  r.after=csrs(); r.csr_bad=!!(r.after.f!=8 || r.after.v!=2 || r.after.s);
  proof_t full=validate(0,first);
  r.bytes=full.out.checked*4+full.q8.checked+full.act.checked+full.input.checked+
      full.weight.checked+full.ws.checked+full.guards.checked;
  r.bad=full.out.errors+full.q8.errors+full.act.errors+full.input.errors+full.weight.errors+
      full.ws.errors+full.guards.errors;
  r.bad+=!!(r.context!=QBS_STATUS_CONTEXT_UNSUPPORTED || r.short_weight!=QBS_STATUS_BUFFER_TOO_SMALL ||
      (E_WS ? r.short_ws!=QBS_STATUS_BUFFER_TOO_SMALL : r.ws_tested!=0) ||
      r.bad_k!=QBS_STATUS_SHAPE || r.bad_segment!=QBS_STATUS_LAYOUT || r.calls || r.csr_bad);
  return r;
}
int main(void) {
  record_t records[2]={0}; proof_t proofs[2]={0}; rejects_t rejected={0}; unsigned completed=0,errors=0;
  memcpy(input.data,boundary_input,IB); memcpy(weights.data,boundary_weights,WB);
  void *guards[]={q8.before,q8.after,activation.before,activation.after,input.before,input.after,
    weights.before,weights.after,output.before,output.after,workspace.before,workspace.after};
  for (unsigned i=0;i<12;++i) memset(guards[i],0xa5,64);
  for (unsigned t=0;t<2;++t) {
    memset(q8.data,0x5a,AB); memset(activation.data,0x5a,AB);
    memset(output.data,0x5a,sizeof(output.data)); memset(workspace.data,0x5a,WS);
    __asm__ volatile("csrwi fcsr, 0\ncsrwi vcsr, 0\ncsrwi vstart, 0":::"memory");
    records[t].before=csrs(); boundary_trial(t,&records[t]); proofs[t]=validate(t,&records[t]); ++completed;
    errors+=records[t].status!=0 || proof_errors(&proofs[t]); if (errors) break;
    if (!t) { rejected=rejection_contract(&records[0]); errors+=rejected.bad!=0; if (errors) break; }
  }
  printf("QBB_META id=%s m=%u n=35 k=2048 stride=38 segment=%u trials=2\n",E_ID,M,E_SEG);
  for (unsigned t=0;t<completed;++t) {
    const record_t *r=&records[t]; const proof_t *p=&proofs[t];
    printf("QBB_TIME trial=%u status=%u fallback=%u t0=%lu t1=%lu t2=%lu t3=%lu t4=%lu t5=%lu\n",
        t,r->status,r->fallback,r->t[0],r->t[1],r->t[2],r->t[3],r->t[4],r->t[5]);
    printf("QBB_CSR trial=%u before_f=%lu before_v=%lu before_s=%lu quant_f=%lu quant_v=%lu quant_s=%lu "
        "pack_f=%lu pack_v=%lu pack_s=%lu after_f=%lu after_v=%lu after_s=%lu\n",t,r->before.f,r->before.v,r->before.s,
        r->quant.f,r->quant.v,r->quant.s,r->pack.f,r->pack.v,r->pack.s,r->after.f,r->after.v,r->after.s);
    printf("QBB_WORK trial=%u planned=%u actual=%u eligible=%u split=%u gather=%u workspace=%zu snapshots=%u coop=%u\n",
        t,r->planned,r->actual,r->eligible,r->plan.split_k,r->plan.needs_activation_gather,
        r->plan.workspace_bytes,r->snapbytes,r->device.capabilities.q4_k_cooperative);
    printf("QBB_PROOF trial=%u out_n=%u out_bad=%u q8_n=%u q8_bad=%u act_n=%u act_bad=%u "
        "input_n=%u input_bad=%u weight_n=%u weight_bad=%u ws_n=%u ws_bad=%u snap_n=%u snap_bad=%u "
        "guard_n=%u guard_bad=%u work_bad=%u csr_bad=%u\n",t,p->out.checked,p->out.errors,p->q8.checked,p->q8.errors,
        p->act.checked,p->act.errors,p->input.checked,p->input.errors,p->weight.checked,p->weight.errors,
        p->ws.checked,p->ws.errors,p->snaps.checked,p->snaps.errors,p->guards.checked,p->guards.errors,p->work_bad,p->csr_bad);
  }
  printf("QBB_REJECT context=%u short_weight=%u short_ws=%u ws_tested=%u bad_k=%u bad_segment=%u calls=%u "
      "bytes=%u bad=%u fcsr=%lu vcsr=%lu vstart=%lu csr_bad=%u\n",rejected.context,rejected.short_weight,
      rejected.short_ws,rejected.ws_tested,rejected.bad_k,rejected.bad_segment,rejected.calls,rejected.bytes,
      rejected.bad,rejected.after.f,rejected.after.v,rejected.after.s,rejected.csr_bad);
  printf("QBB_DONE errors=%u trials=%u\n",errors,completed); return errors!=0 || completed!=2;
}
