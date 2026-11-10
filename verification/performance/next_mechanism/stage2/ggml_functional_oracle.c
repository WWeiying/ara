// Independent host preparation and ordered QBS reference; never linked into guest.
#include "qbs_ref.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
enum { M=8, N=64, K=2048, KB=8, AB=M*KB*292, WB=N*KB*144 };
static void need(int ok) { if (!ok) { fputs("G4_ORACLE_FAIL\n", stderr); exit(1); } }
static void load(const char *path, void *data, size_t size) {
  FILE *f=fopen(path,"rb"); need(f && fread(data,1,size,f)==size && fgetc(f)==EOF); need(!fclose(f));
}
static void save(const char *dir, const char *name, const void *data, size_t size) {
  char path[4096]; need(snprintf(path,sizeof(path),"%s/%s",dir,name)<(int)sizeof(path));
  FILE *f=fopen(path,"wb"); need(f && fwrite(data,1,size,f)==size); need(!fclose(f));
}
int main(int argc,char **argv) {
  need(argc==4);
  float input[M*K], expected[M*N], other[M*N];
  unsigned char raw[128*KB*144], r4[WB], q8[AB], packed[AB];
  load(argv[1],input,sizeof(input)); load(argv[2],raw,sizeof(raw));
  need(qbs_ref_quantize_q8_k(input,M*K,(qbs_block_q8_k_t *)q8,M*KB)==QBS_REF_OK);
  need(qbs_ref_repack_weight_r4(QBS_WEIGHT_PROFILE_Q4_K,raw,WB,N,KB,r4,WB)==QBS_REF_OK);
  save(argv[3],"q8.bin",q8,sizeof(q8));
  for(unsigned mode=0;mode<3;++mode) {
    unsigned tm=mode==0?8:4, rows=mode==2?4:8, tn=mode==0?16:32;
    unsigned flags[4]={0}, count=0;
    uint64_t headers[4]={0};
    unsigned char all[AB];
    for(unsigned row=0;row<rows;row+=tm) {
      if(tm==8) need(qbs_ref_pack_activation_m8_profile(QBS_ACTIVATION_PROFILE_Q8_K,
          q8+row*KB*292,tm*KB*292,tm,KB,packed,sizeof(packed))==QBS_REF_OK);
      else need(qbs_ref_pack_activation_m4_profile(QBS_ACTIVATION_PROFILE_Q8_K,
          q8+row*KB*292,tm*KB*292,KB,packed,sizeof(packed))==QBS_REF_OK);
      memcpy(all+row*KB*292,packed,tm*KB*292);
      for(unsigned col=0;col<N;col+=tn) {
        qbs_descriptor_fields_t fields={.descriptor_version=QBS_DESCRIPTOR_VERSION,
          .weight_profile=QBS_WEIGHT_PROFILE_Q4_K,.activation_profile=QBS_ACTIVATION_PROFILE_Q8_K,
          .weight_layout=QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
          .activation_layout=tm==8?QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED:QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED,
          .n=tn,.k_blocks=KB};
        qbs_descriptor_t d={.header=qbs_pack_descriptor_header(&fields),.weight_base=0x81000000};
        qbs_ref_result_t info;
        float result[256]={0};
        need(qbs_ref_execute(&d,tm,8,1024,0x82000000,r4+col*KB*144,tn*KB*144,
              packed,tm*KB*292,result,256,NULL,NULL,&info)==QBS_REF_OK);
        flags[count]=info.fflags; headers[count++]=d.header;
        for(unsigned r=0;r<tm;++r) for(unsigned c=0;c<tn;++c)
          (mode?other:expected)[(row+r)*N+col+c]=result[r*32+c];
      }
    }
    if(mode) need(!memcmp(expected,other,rows*N*4));
    char name[128];
    snprintf(name,sizeof(name),"workspace_%s.bin",mode==0?"m8":mode==1?"m4":"shape");
    save(argv[3],name,all,rows*KB*292);
    snprintf(name,sizeof(name),"flags_%s.bin",mode==0?"m8":mode==1?"m4":"shape");
    save(argv[3],name,flags,count*4);
    snprintf(name,sizeof(name),"headers_%s.bin",mode==0?"m8":mode==1?"m4":"shape");
    save(argv[3],name,headers,count*8);
  }
  save(argv[3],"output.bin",expected,sizeof(expected));
  puts("G4_ORACLE_PASS outputs=512 quantized_bytes=18688 modes=3");
  return 0;
}
