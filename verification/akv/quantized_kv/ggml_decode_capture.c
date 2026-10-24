/* Reuse the metadata fixture, not its synthetic-data test entry. */
#define main metadata_matrix_main
#include "test_ggml_decode.c"
#undef main
#include <stdlib.h>

static void *load_capture(const char *path,size_t bytes) {
  FILE *file=fopen(path,"rb");
  assert(file && fseek(file,0,SEEK_END)==0 && ftell(file)==(long)bytes);
  rewind(file);
  void *data=malloc(bytes);
  assert(data && fread(data,1,bytes,file)==bytes && fclose(file)==0);
  return data;
}

int main(int argc,char **argv) {
  assert(argc==6 && (argv[1][0]=='0' || argv[1][0]=='1') && argv[1][1]=='\0');
  const unsigned q4=argv[1][0]=='1';
  const size_t row=q4 ? 72u : 136u;
  assert(qbs_device_init_reference(1024,&device)==QBS_STATUS_OK);
  fixture(128,6,2,128,q4,0);
  q.data=load_capture(argv[2],6144); q.nb[1]=512; q.nb[2]=512; q.nb[3]=6144;
  k.data=load_capture(argv[3],512*row); k.ne[1]=256; k.nb[2]=256*row; k.nb[3]=512*row;
  v.data=load_capture(argv[4],69632); v.ne[1]=256; v.nb[2]=34816; v.nb[3]=69632;
  mask.data=load_capture(argv[5],512); mask.ne[0]=256;
  mask.nb[1]=512; mask.nb[2]=512; mask.nb[3]=512;
  dst.data=malloc(6144); assert(dst.data); memset(dst.data,0xa5,6144);
  dst.nb[1]=512; dst.nb[2]=6144; dst.nb[3]=6144;
  context.query_bytes=6144; context.key_bytes=512*row; context.value_bytes=69632;
  context.mask_bytes=512; context.output_bytes=6144;
  dst.op_params[0]=INT32_C(0x3db504f3);
  akv_quant_selection_input_t mapped;
  akv_quant_selection_t selected;
  assert(akv_quant_ggml_map(&dst,&context,&mapped)==AKV_QUANT_GGML_MAP_OK);
  assert(mapped.query.head_stride==512 && mapped.output.head_stride==512 &&
         mapped.key.head_stride==256*row && mapped.key.tokens==256);
  assert(akv_quant_select(&mapped,&selected)==AKV_QUANT_SELECT_OK);
  assert(selected.group_heads==6 && selected.kv_heads==2 && selected.dim==128 &&
         selected.visible_tokens==128 && selected.key_row_bytes==row && selected.query_quant_row_bytes==136);
  for(unsigned i=0;i<6144;++i) assert(((unsigned char *)dst.data)[i]==0xa5);
  printf("GGML_QUANT_CAPTURE_MAP_PASS q4=%u groups=6 kv_heads=2 d=128 capacity=256 visible=128 output_untouched=1 execution=0\n",q4);
  free(q.data); free(k.data); free(v.data); free(mask.data); free(dst.data);
  return 0;
}
