#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "qbs/qbs.h"
#include "qbs_ref.h"
#define NEED(x) do { if (!(x)) { fprintf(stderr,"FAIL line %d\n",__LINE__); exit(1); } } while (0)
enum { N=128,KB=8,AB=8*292,WB=N*8*144 };
static unsigned char weights[WB] __attribute__((aligned(64)));
static unsigned char activation[AB] __attribute__((aligned(64)));
typedef struct { qbs_ref_activation_context_t ref; unsigned mode,trial,commands,flags; } test_t;
static void load(const char *dir,const char *name,void *data,size_t bytes) {
  char path[4096]; NEED(snprintf(path,sizeof(path),"%s/%s",dir,name)<(int)sizeof(path));
  FILE *f=fopen(path,"rb"); NEED(f && fread(data,1,bytes,f)==bytes && fgetc(f)==EOF); NEED(!fclose(f));
}
static uint64_t info(void *p,unsigned index) { (void)p; return qbs_ref_capability_word(index,1024); }
static qbs_status_t execute(void *p,const qbs_descriptor_t *d,unsigned m,const void *a,
                            float *out,size_t stride,unsigned n,int segmented) {
  test_t *t=p; unsigned i=t->commands++;
  unsigned access=t->mode==0 ? 0 : (t->mode==1 ? (i==0 ? 1 : (i==3 ? 3 : 2))
    : (t->trial==0 ? (i==0 ? 1 : 2) : (i==3 ? 3 : 2)));
  qbs_descriptor_fields_t f=qbs_unpack_descriptor_header(d->header);
  NEED(i<4 && m==1 && n==32 && stride==N && !segmented && f.activation_access==access);
  NEED(f.context_id==0 && f.context_generation==(t->mode ? (t->mode==2 ? 1 : t->trial+1) : 0));
  float result[32]; qbs_ref_result_t r;
  NEED(qbs_ref_execute_with_context(&t->ref,d,m,8,1024,(uintptr_t)a,
      (const void *)(uintptr_t)d->weight_base,32*KB*144,a,AB,result,32,NULL,NULL,&r)==QBS_REF_OK);
  memcpy(out,result,32*4); t->flags|=r.fflags;
  return QBS_STATUS_OK;
}
int main(int argc,char **argv) {
  NEED(argc==2);
  float golden[N],out[N]; load(argv[1],"weights_r4.bin",weights,WB);
  load(argv[1],"expected_q8.bin",activation,AB); load(argv[1],"expected.bin",golden,sizeof(golden));
  qbs_device_t device; qbs_plan_t plan;
  qbs_problem_t problem={.weight_profile=1,.activation_profile=1,.weight_layout=2,
    .activation_storage=1,.m=1,.n=N,.k_elements=2048};
  NEED(qbs_device_query(info,NULL,&device)==QBS_STATUS_OK);
  NEED(qbs_plan_create(&device,&problem,&plan)==QBS_STATUS_OK);
  NEED(qbs_plan_supports_activation_context(&plan));
  for (unsigned mode=0;mode<3;++mode) {
    test_t t={.mode=mode}; qbs_ref_activation_context_reset(&t.ref);
    for (unsigned trial=0;trial<2;++trial) {
      t.trial=trial; t.commands=0; memset(out,0x5a,sizeof(out));
      qbs_execution_options_t options={.use_activation_context=mode!=0,
        .activation_context={0,mode==2 ? 1 : trial+1},
        .activation_context_scope=mode==2 ? (trial ? 3 : 1) : 0};
      NEED(qbs_execute_with_options(&plan,weights,WB,activation,AB,out,N,N,NULL,0,&options,execute,&t)==QBS_STATUS_OK);
      NEED(t.commands==4 && !memcmp(out,golden,sizeof(out)));
      NEED(!!t.ref.valid==(mode==2 && trial==0));
    }
  }
  puts("CONTEXT_REAL_HOST_PASS modes=3 calls=6 commands=24 full_outputs_checked=768 operation_release_and_cross_call_lifecycle=checked");
  return 0;
}
