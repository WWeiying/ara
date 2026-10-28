#include "prefix_schedule.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>

typedef struct { unsigned commands,values,panels,key_rows,dot_rows,last,maximum; } counts_t;
static int qk(void *opaque,unsigned first,unsigned rows,unsigned token,unsigned n,float *out,size_t stride) {
  counts_t *c=opaque;(void)first;
  ++c->commands;c->dot_rows+=rows*n;
  if(c->last!=token) {
    ++c->panels;c->last=token;
    unsigned count=c->maximum-token;c->key_rows+=count<32?count:32;
  }
  for(unsigned r=0;r<rows;++r) for(unsigned t=0;t<n;++t) out[r*stride+t]=0;
  return 0;
}
static int value(void *opaque,unsigned token,float *out,unsigned dim) {
  counts_t *c=opaque;(void)token;++c->values;
  for(unsigned i=0;i<dim;++i) out[i]=1;
  return 0;
}
static void scale(int n,float *out,float s) { for(int i=0;i<n;++i) out[i]*=s; }
static void mad(int n,float *out,const float *v,float s) { for(int i=0;i<n;++i) out[i]+=v[i]*s; }

static counts_t execute(unsigned queries,unsigned gqa,unsigned past,int shared) {
  counts_t total={0};unsigned all=queries*gqa;
  akv_quant_online_workspace_t work;
  float output[8][32];
  for(unsigned first=0;first<all;) {
    unsigned rows=shared?8:gqa;if(rows>all-first)rows=all-first;
    unsigned visible[8],maximum=0;
    for(unsigned r=0;r<rows;++r) {
      visible[r]=past+(first+r)/gqa+1;
      if(visible[r]>maximum)maximum=visible[r];
    }
    counts_t c={.last=UINT_MAX,.maximum=maximum};
    akv_quant_online_plan_t plan={rows,32,maximum,1,&c,qk,value,scale,mad};
    int status=shared?quant_prefill_prefix_schedule(&plan,visible,output[0],32,&work):
                      akv_quant_online_shared(&plan,output[0],32,&work);
    assert(status==AKV_QUANT_OK);
    for(unsigned r=0;r<rows;++r) for(unsigned d=0;d<32;++d)
      assert(isfinite(output[r][d]) && fabsf(output[r][d]-1)<1e-5f);
    total.commands+=c.commands;total.values+=c.values;total.panels+=c.panels;
    total.key_rows+=c.key_rows;total.dot_rows+=c.dot_rows;first+=rows;
  }
  return total;
}

int main(void) {
  const unsigned queries[]={2,4,8,16,40},past[]={0,16,31,64};
  puts("queries,gqa,past,base_commands,new_commands,base_v,new_v,base_panels,new_panels,base_key_rows,new_key_rows,dot_rows");
  for(unsigned qi=0;qi<5;++qi) for(unsigned g=1;g<=8;++g) for(unsigned pi=0;pi<4;++pi) {
    counts_t a=execute(queries[qi],g,past[pi],0),b=execute(queries[qi],g,past[pi],1);
    unsigned expected=g*(queries[qi]*past[pi]+queries[qi]*(queries[qi]+1)/2);
    assert(a.dot_rows==expected && b.dot_rows==expected);
    printf("%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u\n",queries[qi],g,past[pi],
      a.commands,b.commands,a.values,b.values,a.panels,b.panels,a.key_rows,b.key_rows,expected);
  }
}
