#include "admission.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

static void *load(const char *root,const char *name,size_t bytes) {
  char path[4096];int n=snprintf(path,sizeof(path),"%s/%s",root,name);
  assert(n>0 && (size_t)n<sizeof(path));
  FILE *file=fopen(path,"rb");assert(file);
  void *data=malloc(bytes);assert(data);
  assert(fread(data,1,bytes,file)==bytes && fgetc(file)==EOF);
  assert(!fclose(file));return data;
}
int main(int argc,char **argv) {
  assert(argc==3 && (!strcmp(argv[2],"q4_0") || !strcmp(argv[2],"q8_0")));
  unsigned q4=!strcmp(argv[2],"q4_0"),row=q4?72:136;
  void *q=load(argv[1],"attn_q_input-0.bin",163840);
  void *k=load(argv[1],"attn_k_input-0.bin",row*256*8);
  void *v=load(argv[1],"attn_v_input-0.bin",278528);
  void *mask=load(argv[1],"attn_mask_input-0.bin",10240);
  void *output=malloc(163840);assert(output);memset(output,0xa5,163840);
  qbs_device_t device;assert(qbs_device_init_reference(1024,&device)==QBS_STATUS_OK);
  quant_prefill_input_t request={.tensors={
    .requested=1,.vlen_bits=1024,.normal_memory=1,.device=&device,
    .key_encoding=q4?QBS_WEIGHT_ENCODING_Q4_0:QBS_WEIGHT_ENCODING_Q8_0_WEIGHT,
    .value_encoding=QBS_WEIGHT_ENCODING_Q8_0_WEIGHT,
    .query={q,163840,512,10240,128,20,16},
    .key={k,row*256*8,row,row*256,128,256,8},
    .value={v,278528,136,34816,128,256,8},
    .output={output,163840,8192,512,128,20,16},
    .mask=mask,.mask_bytes=10240},.mask_row_stride=512};
  uint32_t scale=0x3db504f3;memcpy(&request.tensors.scale,&scale,4);
  quant_prefill_admission_t plan;
  assert(quant_prefill_admit(&request,&plan)==AKV_QUANT_SELECT_OK);
  assert(plan.queries==20 && plan.common.visible_tokens==20 &&
         plan.common.kv_heads==8 && plan.common.group_heads==2);
  for(unsigned t=0;t<20;++t) assert(plan.visible[t]==t+1);
  for(unsigned i=0;i<163840;++i) assert(((unsigned char *)output)[i]==0xa5);
  printf("REAL_PREFILL_ADMISSION_PASS key=%s queries=20 q_heads=16 kv_heads=8 dim=128 commands=0\n",argv[2]);
  free(q);free(k);free(v);free(mask);free(output);
}
