#include "software/akv/experimental/quantized_kv/ggml_decode.h"
#include <assert.h>
#include <fenv.h>
#include <stdio.h>

static float query[16*260] __attribute__((aligned(64)));
static float output[16*264] __attribute__((aligned(64)));
static unsigned char key[2*128*272] __attribute__((aligned(64)));
static unsigned char value[2*128*272] __attribute__((aligned(64)));
static uint16_t masks[128] __attribute__((aligned(64)));
static struct ggml_tensor q,k,v,mask,dst;
static qbs_device_t device;
static akv_quant_ggml_context_t context;
static unsigned accepted,rejected,deferred;

static void tensor(struct ggml_tensor *t,enum ggml_type type,void *data,
    unsigned a,unsigned b,unsigned c,size_t block,size_t row,size_t head) {
  memset(t,0,sizeof(*t)); t->type=type; t->data=data;
  t->ne[0]=a; t->ne[1]=b; t->ne[2]=c; t->ne[3]=1;
  t->nb[0]=block; t->nb[1]=row; t->nb[2]=head; t->nb[3]=head*c;
}

static void fixture(unsigned d,unsigned groups,unsigned heads,unsigned prefix,unsigned q4,unsigned interleaved) {
  const unsigned all_heads=groups*heads;
  const size_t kr=d/32*(q4 ? 18u : 34u),vr=d/32*34u;
  tensor(&q,GGML_TYPE_F32,query,d,1,all_heads,4,d*4,(d+4)*4);
  tensor(&k,q4 ? GGML_TYPE_Q4_0 : GGML_TYPE_Q8_0,key,d,128,heads,q4 ? 18 : 34,kr,128*kr);
  tensor(&v,GGML_TYPE_Q8_0,value,d,128,heads,34,interleaved ? heads*vr : vr,interleaved ? vr : 128*vr);
  tensor(&mask,GGML_TYPE_F16,masks,128,1,1,2,256,256);
  tensor(&dst,GGML_TYPE_F32,output,d,all_heads,1,4,(d+8)*4,all_heads*(d+8)*4);
  dst.op=GGML_OP_FLASH_ATTN_EXT;
  dst.src[0]=&q; dst.src[1]=&k; dst.src[2]=&v; dst.src[3]=&mask;
  const float scale=0.0883883461356163f;
  memcpy(dst.op_params,&scale,4);
  for(unsigned i=0;i<128;++i) masks[i]=i<prefix ? 0 : UINT16_C(0xfc00);
  memset(&context,0,sizeof(context));
  context.requested=1; context.nth=1; context.vlen_bits=1024; context.normal_memory=1;
  context.device=&device; context.query_bytes=all_heads*(d+4)*4;
  context.key_bytes=heads*128*kr; context.value_bytes=heads*128*vr;
  context.mask_bytes=sizeof(masks); context.output_bytes=all_heads*(d+8)*4;
}

static void rejected_unchanged(int reason) {
  akv_quant_selection_input_t mapped,before;
  memset(&mapped,0xa5,sizeof(mapped)); memcpy(&before,&mapped,sizeof(before));
  assert(akv_quant_ggml_map(&dst,&context,&mapped)==reason);
  assert(!memcmp(&mapped,&before,sizeof(mapped))); ++rejected;
}

static void selection_rejected(int reason) {
  akv_quant_selection_input_t mapped;
  akv_quant_selection_t selection,before;
  assert(akv_quant_ggml_map(&dst,&context,&mapped)==AKV_QUANT_GGML_MAP_OK);
  memset(&selection,0xa5,sizeof(selection)); memcpy(&before,&selection,sizeof(before));
  assert(akv_quant_select(&mapped,&selection)==reason);
  assert(!memcmp(&selection,&before,sizeof(selection))); ++deferred;
}

int main(void) {
  assert(qbs_device_init_reference(1024,&device)==QBS_STATUS_OK);
  memset(output,0xa5,sizeof(output));
  const unsigned prefixes[]={1,31,33,128};
  for(unsigned d=32;d<=256;d+=32)
    for(unsigned g=1;g<=8;++g)
      for(unsigned h=1;h<=2;++h)
        for(unsigned pi=0;pi<4;++pi)
          for(unsigned q4=0;q4<2;++q4)
            for(unsigned interleaved=0;interleaved<2;++interleaved) {
              fixture(d,g,h,prefixes[pi],q4,interleaved);
              akv_quant_selection_input_t mapped;
              akv_quant_selection_t selected;
              assert(akv_quant_ggml_map(&dst,&context,&mapped)==AKV_QUANT_GGML_MAP_OK);
              assert(mapped.query.head_stride==q.nb[2] && mapped.output.head_stride==dst.nb[1]);
              assert(mapped.key.token_stride==k.nb[1] && mapped.value.head_stride==v.nb[2]);
              assert(mapped.query.data==query && mapped.key.data==key && mapped.value.data==value && mapped.output.data==output);
              assert(mapped.query.heads==g*h && mapped.output.heads==g*h);
              assert(akv_quant_select(&mapped,&selected)==AKV_QUANT_SELECT_OK);
              assert(selected.group_heads==g && selected.kv_heads==h && selected.dim==d &&
                  selected.visible_tokens==prefixes[pi] && selected.key_row_bytes==d/32*(q4 ? 18u : 34u));
              ++accepted;
            }
#define RESET() fixture(128,6,2,65,0,0)
#define REJECT(change,reason) do { RESET(); change; rejected_unchanged(reason); } while(0)
  REJECT(context.requested=0,AKV_QUANT_GGML_MAP_DISABLED);
  REJECT(context.requested=2,AKV_QUANT_GGML_MAP_DISABLED);
  REJECT(context.use_ref=1,AKV_QUANT_GGML_MAP_DISABLED);
  REJECT(context.nth=2,AKV_QUANT_GGML_MAP_THREADING);
  REJECT(context.ith=1,AKV_QUANT_GGML_MAP_THREADING);
  REJECT(dst.op=GGML_OP_MUL_MAT,AKV_QUANT_GGML_MAP_OPERATION);
  REJECT(dst.op_params[3]=123,AKV_QUANT_GGML_MAP_OPERATION);
  REJECT(dst.src[5]=&q,AKV_QUANT_GGML_MAP_OPERATION);
  REJECT(dst.src[0]=NULL,AKV_QUANT_GGML_MAP_TYPE);
  REJECT(dst.src[3]=NULL,AKV_QUANT_GGML_MAP_TYPE);
  REJECT(k.type=GGML_TYPE_Q4_K,AKV_QUANT_GGML_MAP_TYPE);
  REJECT(v.type=GGML_TYPE_F16,AKV_QUANT_GGML_MAP_TYPE);
  REJECT(q.ne[1]=2,AKV_QUANT_GGML_MAP_SHAPE);
  REJECT(q.ne[3]=2,AKV_QUANT_GGML_MAP_SHAPE);
  REJECT(q.ne[0]=-1,AKV_QUANT_GGML_MAP_SHAPE);
  REJECT(q.ne[2]=(int64_t)UINT32_MAX+1,AKV_QUANT_GGML_MAP_SHAPE);
  REJECT(dst.ne[1]=1,AKV_QUANT_GGML_MAP_SHAPE);
  REJECT(dst.ne[2]=2,AKV_QUANT_GGML_MAP_SHAPE);
  REJECT(mask.ne[2]=2,AKV_QUANT_GGML_MAP_SHAPE);
  REJECT(mask.ne[0]=64,AKV_QUANT_GGML_MAP_SHAPE);
  REJECT(k.nb[0]=4,AKV_QUANT_GGML_MAP_LAYOUT);
  REJECT(v.nb[0]=4,AKV_QUANT_GGML_MAP_LAYOUT);
  REJECT(dst.nb[0]=8,AKV_QUANT_GGML_MAP_LAYOUT);
#define DEFER(change,reason) do { RESET(); change; selection_rejected(reason); } while(0)
  DEFER(context.query_bytes=1,AKV_QUANT_SELECT_LAYOUT);
  DEFER(context.output_bytes=1,AKV_QUANT_SELECT_LAYOUT);
  DEFER(context.mask_bytes=1,AKV_QUANT_SELECT_MASK);
  DEFER(dst.src[4]=&q,AKV_QUANT_SELECT_FEATURE);
  DEFER(context.vstart=1,AKV_QUANT_SELECT_CAPABILITY);
  DEFER(context.normal_memory=0,AKV_QUANT_SELECT_CAPABILITY);
  DEFER(context.frm=1,AKV_QUANT_SELECT_CAPABILITY);
  DEFER(context.device=NULL,AKV_QUANT_SELECT_CAPABILITY);
  DEFER(k.nb[1]+=2,AKV_QUANT_SELECT_LAYOUT);
  DEFER(q.data=NULL,AKV_QUANT_SELECT_LAYOUT);
  DEFER(masks[32]=UINT16_C(0xfc00),AKV_QUANT_SELECT_MASK);
  DEFER(dst.data=query,AKV_QUANT_SELECT_ALIAS);
  RESET(); dst.op_params[0]=INT32_C(0x7f800001);
  feclearexcept(FE_ALL_EXCEPT);
  selection_rejected(AKV_QUANT_SELECT_FEATURE);
  assert(!fetestexcept(FE_INVALID));
  RESET(); dst.op_params[3]=GGML_PREC_F32;
  akv_quant_selection_input_t mapped;
  assert(akv_quant_ggml_map(&dst,&context,&mapped)==AKV_QUANT_GGML_MAP_OK);
  assert(akv_quant_ggml_map(NULL,&context,&mapped)==AKV_QUANT_GGML_MAP_OPERATION);
  assert(akv_quant_ggml_map(&dst,NULL,&mapped)==AKV_QUANT_GGML_MAP_DISABLED);
  assert(akv_quant_ggml_map(&dst,&context,NULL)==AKV_QUANT_GGML_MAP_DISABLED);
  for(unsigned i=0;i<sizeof(output);++i) assert(((unsigned char *)output)[i]==0xa5);
  printf("GGML_QUANT_MAP_PASS accepted=%u rejected=%u deferred=%u output_untouched=1 snan_no_invalid=1\n",
         accepted,rejected,deferred);
  return 0;
}
