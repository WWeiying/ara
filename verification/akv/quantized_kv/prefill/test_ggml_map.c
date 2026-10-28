#include "ggml_map.h"
#include <assert.h>
#include <stdio.h>

static float query[256*2*128], output[256*2*128];
static unsigned char key[256*136], value[256*136];
static uint16_t masks[256*256];
static struct ggml_tensor q,k,v,mask,dst;
static akv_quant_ggml_context_t context;
static unsigned accepted, rejected;

static void tensor(struct ggml_tensor *t, enum ggml_type type, void *data,
    unsigned a,unsigned b,unsigned c,size_t block,size_t row,size_t head) {
  memset(t,0,sizeof(*t));t->type=type;t->data=data;
  t->ne[0]=a;t->ne[1]=b;t->ne[2]=c;t->ne[3]=1;
  t->nb[0]=block;t->nb[1]=row;t->nb[2]=head;t->nb[3]=head*c;
}

static void fixture(unsigned queries,unsigned q4,unsigned padded) {
  tensor(&q,GGML_TYPE_F32,query,128,queries,2,4,512,queries*512);
  tensor(&k,q4?GGML_TYPE_Q4_0:GGML_TYPE_Q8_0,key,128,256,1,
         q4?18:34,q4?72:136,256*(q4?72:136));
  tensor(&v,GGML_TYPE_Q8_0,value,128,256,1,34,136,256*136);
  tensor(&mask,GGML_TYPE_F16,masks,256,padded?256:queries,1,2,512,256*512);
  tensor(&dst,GGML_TYPE_F32,output,128,2,queries,4,512,1024);
  dst.op=GGML_OP_FLASH_ATTN_EXT;
  dst.src[0]=&q;dst.src[1]=&k;dst.src[2]=&v;dst.src[3]=&mask;
  memset(&context,0,sizeof(context));context.requested=1;context.nth=1;
  context.query_bytes=sizeof(query);context.key_bytes=sizeof(key);
  context.value_bytes=sizeof(value);context.output_bytes=sizeof(output);
  context.mask_bytes=sizeof(masks);
}

static void reject(int reason) {
  quant_prefill_input_t mapped,before;
  memset(&mapped,0xa5,sizeof(mapped));memcpy(&before,&mapped,sizeof(before));
  assert(quant_prefill_ggml_map(&dst,&context,&mapped)==reason);
  assert(!memcmp(&mapped,&before,sizeof(mapped)));++rejected;
}

int main(void) {
  unsigned counts[]={1,2,4,20,256};
  memset(output,0xa5,sizeof(output));
  for(unsigned i=0;i<5;++i) for(unsigned q4=0;q4<2;++q4) for(unsigned pad=0;pad<2;++pad) {
    fixture(counts[i],q4,pad);
    struct ggml_tensor saved[]={q,k,v,mask,dst};
    quant_prefill_input_t mapped;
    assert(quant_prefill_ggml_map(&dst,&context,&mapped)==AKV_QUANT_GGML_MAP_OK);
    assert(mapped.tensors.query.tokens==counts[i] && mapped.tensors.output.tokens==counts[i]);
    assert(mapped.tensors.query.token_stride==512 && mapped.tensors.query.head_stride==counts[i]*512);
    assert(mapped.tensors.output.token_stride==1024 && mapped.tensors.output.head_stride==512);
    assert(mapped.mask_row_stride==512 && mapped.tensors.mask==masks);
    assert(mapped.tensors.query.data==query && mapped.tensors.output.data==output);
    assert(!memcmp(saved,(struct ggml_tensor[]){q,k,v,mask,dst},sizeof(saved)));
    ++accepted;
  }
#define REJECT(change,reason) do {fixture(20,1,0);change;reject(reason);} while(0)
  REJECT(context.nth=2,AKV_QUANT_GGML_MAP_THREADING);
  REJECT(context.use_ref=1,AKV_QUANT_GGML_MAP_DISABLED);
  REJECT(dst.op=GGML_OP_MUL_MAT,AKV_QUANT_GGML_MAP_OPERATION);
  REJECT(dst.src[0]=NULL,AKV_QUANT_GGML_MAP_TYPE);
  REJECT(dst.src[3]=NULL,AKV_QUANT_GGML_MAP_TYPE);
  REJECT(q.ne[1]=257,AKV_QUANT_GGML_MAP_SHAPE);
  REJECT(q.ne[1]=0,AKV_QUANT_GGML_MAP_SHAPE);
  REJECT(mask.ne[1]=19,AKV_QUANT_GGML_MAP_SHAPE);
  REJECT(dst.ne[2]=19,AKV_QUANT_GGML_MAP_SHAPE);
  REJECT(q.ne[3]=2,AKV_QUANT_GGML_MAP_SHAPE);
  REJECT(mask.ne[2]=2,AKV_QUANT_GGML_MAP_SHAPE);
  REJECT(k.type=GGML_TYPE_Q4_K,AKV_QUANT_GGML_MAP_TYPE);
  REJECT(v.type=GGML_TYPE_F16,AKV_QUANT_GGML_MAP_TYPE);
  REJECT(q.nb[0]=8,AKV_QUANT_GGML_MAP_LAYOUT);
  REJECT(dst.src[5]=&q,AKV_QUANT_GGML_MAP_OPERATION);
  REJECT(dst.op_params[3]=123,AKV_QUANT_GGML_MAP_OPERATION);
  for(unsigned i=0;i<sizeof(output);++i) assert(((unsigned char *)output)[i]==0xa5);
  printf("PREFILL_GGML_MAP_PASS accepted=%u rejected=%u metadata_unchanged=1 execution=0\n",accepted,rejected);
  return 0;
}
