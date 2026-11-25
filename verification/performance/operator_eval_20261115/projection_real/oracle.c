#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "qbs/qbs.h"
#include "qbs_ref.h"

static void require(int ok, const char *s) { if (!ok) { fprintf(stderr,"%s\n",s); exit(1); } }
static void load(const char *path, void *p, size_t n) {
  FILE *f=fopen(path,"rb"); require(f && fread(p,1,n,f)==n && fgetc(f)==EOF,"Input size");
  require(!fclose(f),"Input close");
}
static void save(const char *dir, const char *name, const void *p, size_t n) {
  char path[4096]; require(snprintf(path,sizeof(path),"%s/%s",dir,name)<(int)sizeof(path),"Path");
  FILE *f=fopen(path,"wb"); require(f && fwrite(p,1,n,f)==n && !fclose(f),"Output");
}
static uint64_t info(void *opaque, unsigned index) { (void)opaque; return qbs_ref_capability_word(index,1024); }
int main(int argc, char **argv) {
  require(argc==8,"oracle PROFILE M N K INPUT WEIGHTS DIR");
  unsigned profile=(unsigned)atoi(argv[1]), m=(unsigned)atoi(argv[2]);
  unsigned N=(unsigned)atoi(argv[3]), K=(unsigned)atoi(argv[4]);
  require((N==64 || N==128) && K && K<=65536 && K%256==0,"N/full K");
  qbs_weight_profile_info_t wi;
  qbs_activation_profile_info_t ai;
  require((m==1 || m==4) && qbs_weight_profile_info(profile,&wi)==QBS_STATUS_OK,"Profile/M");
  unsigned ap=qbs_default_activation_profile(profile);
  require(qbs_activation_profile_info(ap,&ai)==QBS_STATUS_OK && wi.block_elements==ai.block_elements,"Activation ABI");
  unsigned kb=K/wi.block_elements, ab=m*kb*ai.block_bytes, wb=N*kb*wi.block_bytes;
  float *input=malloc(m*K*4), *expected=calloc(m*N,4);
  unsigned char *weights=malloc(wb), *r4=malloc(wb), *row=malloc(ab), *packed=malloc(ab), *sdkpack=malloc(ab);
  require(input && expected && weights && r4 && row && packed && sdkpack,"Allocation");
  unsigned seen[4*128]={0}, flags=0, count=0;
  load(argv[5],input,m*K*4); load(argv[6],weights,wb);
  require((ap==1 ? qbs_ref_quantize_q8_k(input,m*K,(void *)row,m*kb) :
           qbs_ref_quantize_q8_0(input,m*K,(void *)row,m*kb))==QBS_REF_OK,"Independent quantizer");
  require(qbs_ref_repack_weight_r4(profile,weights,wb,N,kb,r4,wb)==QBS_REF_OK,"Independent R4");
  if (m==4) {
    require(qbs_ref_pack_activation_m4_profile(ap,row,ab,kb,packed,ab)==QBS_REF_OK,"Independent M4");
    require(qbs_pack_activation_m4(ap,row,ab,kb,sdkpack,ab)==QBS_STATUS_OK,"SDK M4");
  } else { memcpy(packed,row,ab); memcpy(sdkpack,row,ab); }
  require(!memcmp(packed,sdkpack,ab),"SDK/reference packing disagreement");
  qbs_device_t device; qbs_plan_t plan;
  qbs_problem_t problem={.weight_profile=profile,.activation_profile=ap,.weight_layout=2,
    .activation_storage=m==4 ? 2 : 1,.m=m,.n=N,.k_elements=K};
  require(qbs_device_query(info,NULL,&device)==QBS_STATUS_OK &&
          qbs_plan_create(&device,&problem,&plan)==QBS_STATUS_OK,"Planner");
  require(!plan.split_k && !plan.needs_activation_gather && !plan.workspace_bytes && plan.k_blocks==kb,"Full K direct");
  printf("{\"activation_profile\":%u,\"activation_block_bytes\":%u,\"weight_block_bytes\":%u,\"k_blocks\":%u,\"commands\":[",ap,ai.block_bytes,wi.block_bytes,kb);
  qbs_plan_cursor_t cursor; qbs_plan_cursor_reset(&cursor);
  for (;;) {
    qbs_command_t c; int has;
    require(qbs_plan_next(&plan,&cursor,&c,&has)==QBS_STATUS_OK,"Cursor"); if (!has) break;
    require(c.k_blocks==kb && !c.k_block_start && !c.accumulate && !c.gather_activation,"Direct command");
    qbs_descriptor_fields_t f={.descriptor_version=QBS_DESCRIPTOR_VERSION,.weight_profile=profile,
      .activation_profile=ap,.weight_layout=2,.activation_layout=c.activation_layout,.n=c.n,.k_blocks=kb};
    qbs_descriptor_t d={.header=qbs_pack_descriptor_header(&f),.weight_base=0x81000000};
    float result[256]={0}; qbs_ref_result_t ri;
    require(qbs_ref_execute(&d,c.m,8,1024,0x82000000,r4+c.weight_offset_bytes,c.n*kb*wi.block_bytes,
      packed+c.activation_offset_bytes,c.m*kb*ai.block_bytes,result,256,NULL,NULL,&ri)==QBS_REF_OK,"Independent command");
    flags|=ri.fflags;
    for (unsigned r=0;r<c.m;++r) for (unsigned n=0;n<c.n;++n) {
      unsigned index=(c.input_start+r)*N+c.output_start+n;
      require(index<m*N && !seen[index]++,"Duplicate/OOB output"); expected[index]=result[r*32+n];
    }
    printf("%s{\"m\":%u,\"n\":%u,\"row\":%u,\"col\":%u,\"layout\":%u}",count ? "," : "",c.m,c.n,c.input_start,c.output_start,c.activation_layout);
    ++count;
  }
  for (unsigned i=0;i<m*N;++i) require(seen[i]==1,"Missing output");
  printf("],\"flags\":%u,\"outputs\":%u}\n",flags,m*N);
  save(argv[7],"weights_r4.bin",r4,wb); save(argv[7],"expected_q8.bin",row,ab);
  save(argv[7],"expected_packed.bin",packed,ab); save(argv[7],"expected.bin",expected,m*N*4);
  free(sdkpack); free(packed); free(row); free(r4); free(weights); free(expected); free(input);
  return 0;
}
