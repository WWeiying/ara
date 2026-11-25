#include <fenv.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "qbs/qbs.h"
#include "qbs_ref.h"
#include "config.h"
enum { M=E_M,N=35,K=2048,KB=8,PN=36,S=38,AB=M*KB*292,WB=PN*KB*144,MAXC=6,MAXWS=4096 };
#define NEED(x) do { if (!(x)) { fprintf(stderr,"oracle line %d\n",__LINE__); exit(1); } } while (0)
typedef struct { qbs_command_t c; unsigned snapshot; } command_t;
static command_t cmds[MAXC];
static unsigned char r4[WB] __attribute__((aligned(64))),q8[AB] __attribute__((aligned(64)));
static unsigned char snaps[2*AB],workspace[MAXWS] __attribute__((aligned(64)));
static unsigned commands,snapbytes,flags;
static unsigned hostflags(void) {
  int f=fetestexcept(FE_ALL_EXCEPT);
  return ((f&FE_INVALID)?16:0)|((f&FE_DIVBYZERO)?8:0)|((f&FE_OVERFLOW)?4:0)|
         ((f&FE_UNDERFLOW)?2:0)|((f&FE_INEXACT)?1:0);
}
static void load(const char *path,void *p,size_t n) {
  FILE *f=fopen(path,"rb"); NEED(f && fread(p,1,n,f)==n && fgetc(f)==EOF); NEED(!fclose(f));
}
static void save(const char *dir,const char *name,const void *p,size_t n) {
  char path[4096]; NEED(snprintf(path,sizeof(path),"%s/%s",dir,name)<(int)sizeof(path));
  FILE *f=fopen(path,"wb"); NEED(f && fwrite(p,1,n,f)==n && !fclose(f));
}
static uint64_t info(void *p,unsigned i) { (void)p; return qbs_ref_capability_word(i,1024); }
static qbs_status_t rejected(void *p,const qbs_descriptor_t *d,unsigned m,const void *a,
    float *out,size_t stride,unsigned n,int split) {
  (void)d;(void)m;(void)a;(void)out;(void)stride;(void)n;(void)split;
  ++*(unsigned *)p; return QBS_STATUS_EXECUTION;
}
typedef struct { unsigned count,flags; } observed_t;
static qbs_status_t execute(void *p,const qbs_descriptor_t *d,unsigned m,const void *a,
                            float *out,size_t stride,unsigned n,int split) {
  observed_t *o=p; NEED(o->count<commands);
  command_t *e=&cmds[o->count++]; qbs_command_t *c=&e->c;
  qbs_descriptor_fields_t f=qbs_unpack_descriptor_header(d->header);
  NEED(m==M && n==c->n && f.k_blocks==c->k_blocks && f.activation_access==0 &&
       f.activation_layout==1 && split==!!E_SEG && stride==(E_SEG ? n : S));
  NEED(d->weight_base==(uintptr_t)(r4+c->weight_offset_bytes));
  NEED(!memcmp(a,snaps+e->snapshot,M*c->k_blocks*292));
  o->flags|=hostflags();
  float result[128]; qbs_ref_result_t ri;
  NEED(qbs_ref_execute(d,m,8,1024,(uintptr_t)a,(const void *)(uintptr_t)d->weight_base,
      ((n+3)/4*4)*c->k_blocks*144,a,M*c->k_blocks*292,result,128,NULL,NULL,&ri)==QBS_REF_OK);
  o->flags|=ri.fflags;
  for (unsigned r=0;r<M;++r) for (unsigned j=0;j<n;++j) out[r*stride+j]=result[r*32+j];
  return QBS_STATUS_OK;
}
int main(int argc,char **argv) {
  NEED(argc==4 && !fesetround(FE_TONEAREST));
  float input[M*K],expected[M*S],actual[M*S]; unsigned char row[N*KB*144],sdk_r4[WB],goldws[MAXWS];
  load(argv[1],input,sizeof(input)); load(argv[2],row,sizeof(row));
  NEED(qbs_ref_quantize_q8_k(input,M*K,(qbs_block_q8_k_t *)q8,M*KB)==QBS_REF_OK);
  memset(r4,0,WB);
  for (unsigned k0=0;k0<KB;) {
    unsigned len=E_SEG && KB-k0>E_SEG ? E_SEG : KB-k0;
    for (unsigned r=0;r<N;++r) for (unsigned k=0;k<len;++k) {
      size_t dst=((size_t)k0*PN+((r/4)*len+k)*4+r%4)*144;
      memcpy(r4+dst,row+(r*KB+k0+k)*144,144);
    }
    k0+=len;
  }
  if (E_SEG) NEED(qbs_repack_weight_r4_segmented(1,row,sizeof(row),N,KB,E_SEG,sdk_r4,WB)==QBS_STATUS_OK);
  else NEED(qbs_repack_weight_r4(1,row,sizeof(row),N,KB,sdk_r4,WB)==QBS_STATUS_OK);
  NEED(!memcmp(r4,sdk_r4,WB));
  qbs_device_t device; qbs_plan_t plan;
  qbs_problem_t problem={.weight_profile=1,.activation_profile=1,.weight_layout=2,
    .activation_storage=1,.m=M,.n=N,.k_elements=K};
  NEED(qbs_device_query(info,NULL,&device)==QBS_STATUS_OK);
  NEED((E_SEG ? qbs_plan_create_segmented_r4(&device,&problem,E_SEG,&plan)
              : qbs_plan_create(&device,&problem,&plan))==QBS_STATUS_OK);
  NEED(!qbs_plan_supports_activation_context(&plan) && plan.split_k==!!E_SEG &&
       plan.needs_activation_gather==!!E_SEG && plan.workspace_bytes<=MAXWS);
  unsigned seen[M*N*KB]={0}; memset(expected,0x5a,sizeof(expected)); memset(goldws,0x5a,MAXWS);
  qbs_plan_cursor_t cursor; qbs_plan_cursor_reset(&cursor);
  printf("{\"m\":%u,\"n\":35,\"stride\":38,\"workspace_bytes\":%zu,\"commands\":[",M,plan.workspace_bytes);
  while (1) {
    qbs_command_t c; int has;
    NEED(qbs_plan_next(&plan,&cursor,&c,&has)==QBS_STATUS_OK); if (!has) break;
    NEED(commands<MAXC && c.m==M && c.input_start==0 && c.activation_layout==1);
    unsigned n=N-c.output_start<32 ? N-c.output_start : 32;
    unsigned kb=E_SEG && KB-c.k_block_start>E_SEG ? E_SEG : KB-c.k_block_start;
    size_t wo=E_SEG ? ((size_t)c.k_block_start*PN+c.output_start*kb)*144 : c.output_start*KB*144;
    NEED(c.n==n && c.k_blocks==kb && c.weight_offset_bytes==wo &&
         c.gather_activation==!!E_SEG && c.accumulate==(E_SEG && c.k_block_start!=0));
    cmds[commands]=(command_t){c,snapbytes};
    for (unsigned r=0;r<M;++r)
      memcpy(snaps+snapbytes+r*kb*292,q8+(r*KB+c.k_block_start)*292,kb*292);
    unsigned bytes=M*kb*292;
    if (E_SEG) memcpy(goldws+M*32*4,snaps+snapbytes,bytes);
    qbs_descriptor_fields_t f={.descriptor_version=QBS_DESCRIPTOR_VERSION,.weight_profile=1,
      .activation_profile=1,.weight_layout=2,.activation_layout=1,.n=n,.k_blocks=kb};
    qbs_descriptor_t d={.header=qbs_pack_descriptor_header(&f),.weight_base=0x81000000};
    float result[128]; qbs_ref_result_t ri;
    NEED(qbs_ref_execute(&d,M,8,1024,0x82000000,r4+wo,((n+3)/4*4)*kb*144,
        snaps+snapbytes,bytes,result,128,NULL,NULL,&ri)==QBS_REF_OK);
    flags|=ri.fflags; feclearexcept(FE_ALL_EXCEPT);
    for (unsigned r=0;r<M;++r) for (unsigned col=0;col<n;++col) {
      unsigned index=r*S+c.output_start+col;
      float value=result[r*32+col];
      if (E_SEG) memcpy(goldws+(r*n+col)*4,&value,4);
      if (c.accumulate) { volatile float old=expected[index],part=value; expected[index]=old+part; }
      else expected[index]=value;
      for (unsigned k=0;k<kb;++k) NEED(!seen[(r*N+c.output_start+col)*KB+c.k_block_start+k]++);
    }
    flags|=hostflags();
    printf("%s{\"m\":%u,\"n\":%u,\"kb\":%u,\"k0\":%u,\"col\":%u,\"wo\":%zu,\"snapshot\":%u,\"snapshot_bytes\":%u}",
      commands ? "," : "",M,n,kb,c.k_block_start,c.output_start,wo,snapbytes,bytes);
    snapbytes+=bytes; ++commands;
  }
  for (unsigned i=0;i<M*N*KB;++i) NEED(seen[i]==1);
  unsigned rejected_calls=0;
  for (unsigned trial=0;trial<2;++trial) {
    memset(actual,0x5a,sizeof(actual)); memset(workspace,0x5a,MAXWS); observed_t obs={0};
    feclearexcept(FE_ALL_EXCEPT); qbs_execution_options_t direct={0};
    qbs_status_t status=trial
      ? qbs_execute(&plan,r4,WB,q8,AB,actual,M*S,S,workspace,plan.workspace_bytes,execute,&obs)
      : qbs_execute_with_options(&plan,r4,WB,q8,AB,actual,M*S,S,workspace,plan.workspace_bytes,&direct,execute,&obs);
    obs.flags|=hostflags();
    NEED(status==QBS_STATUS_OK && obs.count==commands && obs.flags==flags &&
         !memcmp(actual,expected,sizeof(actual)) && !memcmp(workspace,goldws,plan.workspace_bytes));
    if (!trial) {
      feclearexcept(FE_ALL_EXCEPT); NEED(!feraiseexcept(FE_DIVBYZERO));
      qbs_execution_options_t context={.use_activation_context=1,.activation_context={0,1}};
      NEED(qbs_execute_with_options(&plan,r4,WB,q8,AB,actual,M*S,S,workspace,plan.workspace_bytes,
                                   &context,rejected,&rejected_calls)==QBS_STATUS_CONTEXT_UNSUPPORTED);
      NEED(qbs_execute(&plan,r4,WB-1,q8,AB,actual,M*S,S,workspace,plan.workspace_bytes,
                       rejected,&rejected_calls)==QBS_STATUS_BUFFER_TOO_SMALL);
      if (plan.workspace_bytes) NEED(qbs_execute(&plan,r4,WB,q8,AB,actual,M*S,S,workspace,
          plan.workspace_bytes-1,rejected,&rejected_calls)==QBS_STATUS_BUFFER_TOO_SMALL);
      qbs_problem_t invalid=problem; qbs_plan_t bad;
      invalid.k_elements=2047; NEED(qbs_plan_create(&device,&invalid,&bad)==QBS_STATUS_SHAPE);
      NEED(qbs_plan_create_segmented_r4(&device,&problem,device.capabilities.max_k_blocks+1,&bad)==QBS_STATUS_LAYOUT);
      NEED(!rejected_calls && hostflags()==8 && !memcmp(actual,expected,sizeof(actual)) &&
           !memcmp(workspace,goldws,plan.workspace_bytes));
    }
  }
  printf("],\"flags\":%u,\"snapshot_bytes\":%u,\"sdk_host_full_outputs_checked\":%u,\"sdk_host_workspace_bytes_checked\":%zu,"
      "\"sdk_host_calls\":2,\"rejected_executor_calls\":%u,\"reject\":{\"context\":%u,\"short_weight\":%u,\"short_ws\":%u,"
      "\"ws_tested\":%u,\"bad_k\":%u,\"bad_segment\":%u}}\n",flags,snapbytes,2*M*S,2*plan.workspace_bytes,rejected_calls,
      QBS_STATUS_CONTEXT_UNSUPPORTED,QBS_STATUS_BUFFER_TOO_SMALL,plan.workspace_bytes ? QBS_STATUS_BUFFER_TOO_SMALL : 0,
      !!plan.workspace_bytes,QBS_STATUS_SHAPE,QBS_STATUS_LAYOUT);
  save(argv[3],"weights.bin",r4,WB); save(argv[3],"q8.bin",q8,AB);
  save(argv[3],"expected.bin",expected,sizeof(expected));
  save(argv[3],"workspace.bin",goldws,plan.workspace_bytes ? plan.workspace_bytes : 4);
  save(argv[3],"activations.bin",snaps,snapbytes);
  return 0;
}
