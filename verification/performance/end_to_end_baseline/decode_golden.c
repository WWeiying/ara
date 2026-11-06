#include "../../qbs/qbs_ref.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { N=128 };
static void need(int ok,const char *why) { if(!ok) {fprintf(stderr,"DECODE_GOLDEN_FAIL %s\n",why);exit(1);} }
static void *load(const char *dir,const char *name,size_t bytes) {
    char path[4096]; need(snprintf(path,sizeof(path),"%s/%s",dir,name)<(int)sizeof(path),"path");
    FILE *f=fopen(path,"rb"); need(f!=NULL,"open"); void *data=malloc(bytes); need(data!=NULL,"allocate");
    need(fread(data,1,bytes,f)==bytes && fgetc(f)==EOF && !ferror(f) && fclose(f)==0,"input size"); return data;
}
static void save(const char *dir,const char *name,const void *data,size_t bytes) {
    char path[4096]; need(snprintf(path,sizeof(path),"%s/%s",dir,name)<(int)sizeof(path),"path");
    FILE *f=fopen(path,"wb");need(f!=NULL,"open output");need(fwrite(data,1,bytes,f)==bytes && fclose(f)==0,"write");
}
int main(int argc,char **argv) {
    need(argc==3,"arguments");
    const unsigned *profiles=load(argv[2],"profiles.bin",7*sizeof(unsigned));
    const unsigned stage[]={0,0,0,1,1,2,3};
    const char *sources[]={"attn_norm-0","ffn_norm-0","ffn_swiglu-0","result_norm"};
    const char *names[]={"attn_q","attn_v","attn_k","ffn_gate","ffn_up","ffn_down","vocabulary"};
    qbs_block_q8_k_t *activation[4];
    for (unsigned s=0;s<4;++s) {
        const unsigned k=s==2?6144:2048,kb=k/256;
        char name[128];snprintf(name,sizeof(name),"%s_f32.bin",sources[s]);
        const float *input=load(argv[1],name,k*4);activation[s]=malloc(kb*sizeof(*activation[s]));
        need(activation[s]!=NULL && qbs_ref_quantize_q8_k(input,k,activation[s],kb)==QBS_REF_OK,"quantize");
        snprintf(name,sizeof(name),"activation_%u.bin",s);save(argv[2],name,activation[s],kb*sizeof(*activation[s]));
        free((void *)input);
    }
    unsigned flags[7];
    for (unsigned part=0;part<7;++part) {
        need(profiles[part]==QBS_WEIGHT_PROFILE_Q4_K || profiles[part]==QBS_WEIGHT_PROFILE_Q6_K,"profile");
        const unsigned kb=part==5?24:8;
        const size_t row_bytes=kb*qbs_weight_block_bytes(profiles[part]),bytes=N*row_bytes;
        char name[128];snprintf(name,sizeof(name),"%s.bin",names[part]);
        const unsigned char *weights=load(argv[1],name,bytes);unsigned char *packed=malloc(bytes);need(packed!=NULL,"allocate weights");
        need(qbs_ref_repack_weight_r4(profiles[part],weights,bytes,N,kb,packed,bytes)==QBS_REF_OK,"repack");
        float output[N];flags[part]=0;
        for (unsigned start=0;start<N;start+=32) {
            qbs_descriptor_fields_t fields={.descriptor_version=QBS_DESCRIPTOR_VERSION,.weight_profile=profiles[part],
                .activation_profile=QBS_ACTIVATION_PROFILE_Q8_K,.weight_layout=QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                .activation_layout=QBS_ACTIVATION_LAYOUT_ROW_MAJOR,.n=32,.k_blocks=kb};
            qbs_descriptor_t descriptor={.header=qbs_pack_descriptor_header(&fields),.weight_base=0x1000};
            float a[32],b[32];qbs_ref_result_t result={0};
            need(qbs_ref_execute(&descriptor,1,4,1024,0x2000,packed+start*row_bytes,32*row_bytes,
                activation[stage[part]],kb*sizeof(*activation[0]),a,32,NULL,NULL,&result)==QBS_REF_OK,"R4 oracle");
            const unsigned first_flags=result.fflags;flags[part]|=first_flags;
            fields.weight_layout=QBS_WEIGHT_LAYOUT_ROW_MAJOR;descriptor.header=qbs_pack_descriptor_header(&fields);
            need(qbs_ref_execute(&descriptor,1,4,1024,0x2000,weights+start*row_bytes,32*row_bytes,
                activation[stage[part]],kb*sizeof(*activation[0]),b,32,NULL,NULL,&result)==QBS_REF_OK &&
                !memcmp(a,b,sizeof(a)) && result.fflags==first_flags,"Layout oracle mismatch");
            memcpy(output+start,a,sizeof(a));
        }
        snprintf(name,sizeof(name),"part_%u_r4.bin",part);save(argv[2],name,packed,bytes);
        snprintf(name,sizeof(name),"part_%u_expected.bin",part);save(argv[2],name,output,sizeof(output));
        printf("DECODE_GOLDEN part=%u profile=%u k=%u n=128 flags=%u\n",part,profiles[part],kb*256,flags[part]);
        free(packed);free((void *)weights);
    }
    save(argv[2],"flags.bin",flags,sizeof(flags));
    for (unsigned s=0;s<4;++s) free(activation[s]);
    free((void *)profiles);puts("DECODE_GOLDEN_PASS layouts_bitwise=1");return 0;
}
