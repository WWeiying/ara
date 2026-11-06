#include "../../qbs/qbs_ref.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { M=4, N=128 };
static void need(int ok,const char *why) { if(!ok) {fprintf(stderr,"FFN_GOLDEN_FAIL %s\n",why);exit(1);} }
static void *load(const char *dir,const char *name,size_t bytes) {
    char path[4096];need(snprintf(path,sizeof(path),"%s/%s",dir,name)<(int)sizeof(path),"path");
    FILE *f=fopen(path,"rb");need(f!=NULL,"open");void *data=malloc(bytes);need(data!=NULL,"allocate");
    need(fread(data,1,bytes,f)==bytes && fgetc(f)==EOF && !ferror(f) && fclose(f)==0,"input size");return data;
}
static void save(const char *dir,const char *name,const void *data,size_t bytes) {
    char path[4096];need(snprintf(path,sizeof(path),"%s/%s",dir,name)<(int)sizeof(path),"path");
    FILE *f=fopen(path,"wb");need(f!=NULL,"open output");need(fwrite(data,1,bytes,f)==bytes && fclose(f)==0,"write");
}
int main(int argc,char **argv) {
    need(argc==3,"arguments");
    const unsigned *profiles=load(argv[2],"profiles.bin",3*sizeof(unsigned));
    const char *names[]={"ffn_gate","ffn_up","ffn_down"};
    qbs_block_q8_kx4_t *grouped[2];
    for(unsigned stage=0;stage<2;++stage) {
        const unsigned k=stage?6144:2048,kb=k/256;
        const float *input=load(argv[1],stage?"ffn_swiglu-0_f32.bin":"ffn_norm-0_f32.bin",M*k*4);
        qbs_block_q8_k_t *rows=malloc(M*kb*sizeof(*rows));grouped[stage]=malloc(kb*sizeof(*grouped[stage]));
        need(rows && grouped[stage],"allocate activation");
        need(qbs_ref_quantize_q8_k(input,M*k,rows,M*kb)==QBS_REF_OK &&
             qbs_ref_pack_activation_m4(rows,M*kb,kb,grouped[stage],kb)==QBS_REF_OK,"quantize/pack");
        save(argv[2],stage?"down_quantized.bin":"ffn_quantized.bin",grouped[stage],kb*sizeof(*grouped[stage]));
        free(rows);free((void *)input);
    }
    for(unsigned part=0;part<3;++part) {
        need(profiles[part]==QBS_WEIGHT_PROFILE_Q4_K || profiles[part]==QBS_WEIGHT_PROFILE_Q6_K,"profile");
        const unsigned kb=part==2?24:8,stage=part==2;
        const size_t row_bytes=kb*qbs_weight_block_bytes(profiles[part]),bytes=N*row_bytes;
        char name[64];snprintf(name,sizeof(name),"%s.bin",names[part]);
        const unsigned char *weights=load(argv[1],name,bytes);unsigned char *packed=malloc(bytes);need(packed!=NULL,"allocate weights");
        need(qbs_ref_repack_weight_r4(profiles[part],weights,bytes,N,kb,packed,bytes)==QBS_REF_OK,"repack");
        float output[M*N];unsigned flags=0;
        for(unsigned start=0;start<N;start+=32) {
            qbs_descriptor_fields_t fields={.descriptor_version=QBS_DESCRIPTOR_VERSION,.weight_profile=profiles[part],
                .activation_profile=QBS_ACTIVATION_PROFILE_Q8_K,.weight_layout=QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                .activation_layout=QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED,.n=32,.k_blocks=kb};
            qbs_descriptor_t descriptor={.header=qbs_pack_descriptor_header(&fields),.weight_base=0x1000};
            float a[M*32],b[M*32];qbs_ref_result_t result={0};
            need(qbs_ref_execute(&descriptor,M,4,1024,0x2000,packed+start*row_bytes,32*row_bytes,
                 grouped[stage],kb*sizeof(*grouped[stage]),a,M*32,NULL,NULL,&result)==QBS_REF_OK,"R4 reference");
            flags|=result.fflags;fields.weight_layout=QBS_WEIGHT_LAYOUT_ROW_MAJOR;descriptor.header=qbs_pack_descriptor_header(&fields);
            const unsigned first_flags=result.fflags;
            need(qbs_ref_execute(&descriptor,M,4,1024,0x2000,weights+start*row_bytes,32*row_bytes,
                 grouped[stage],kb*sizeof(*grouped[stage]),b,M*32,NULL,NULL,&result)==QBS_REF_OK &&
                 !memcmp(a,b,sizeof(a)) && result.fflags==first_flags,"layout mismatch");
            for(unsigned row=0;row<M;++row) memcpy(output+row*N+start,a+row*32,32*sizeof(float));
        }
        snprintf(name,sizeof(name),"ffn_%u_r4.bin",part);save(argv[2],name,packed,bytes);
        snprintf(name,sizeof(name),"ffn_%u_expected.bin",part);save(argv[2],name,output,sizeof(output));
        snprintf(name,sizeof(name),"ffn_%u_flags.bin",part);save(argv[2],name,&flags,sizeof(flags));
        printf("FFN_GOLDEN part=%u profile=%u k=%u n=128 flags=%u\n",part,profiles[part],kb*256,flags);
        free(packed);free((void *)weights);
    }
    free(grouped[0]);free(grouped[1]);free((void *)profiles);puts("FFN_GOLDEN_PASS layouts_bitwise=1");return 0;
}
