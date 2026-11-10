/* Host-only, unchanged qbs_ref arithmetic; inputs are frozen packed bytes. */
#include "qbs_ref.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void read_file(const char *dir,const char *name,void *data,size_t size) {
    char path[4096];
    if(snprintf(path,sizeof(path),"%s/%s",dir,name)>=(int)sizeof(path)) exit(2);
    FILE *file=fopen(path,"rb");
    if(!file || fread(data,1,size,file)!=size || fgetc(file)!=EOF || fclose(file)) exit(2);
}
int main(int argc,char **argv) {
    if(argc!=3) return 2;
    const unsigned widths[3]={1536,256,256},block[3]={144,210,144},offsets[3]={0,6144,7168};
    const char *names[3]={"q_r4.bin","v_r4.bin","k_r4.bin"};
    unsigned char activation[7008];float output[8192];unsigned flags=0,commands=0;
    read_file(argv[1],"activation_q8k_m4.bin",activation,sizeof(activation));
    for(unsigned part=0;part<3;++part) {
        const size_t bytes=widths[part]*6*block[part];
        void *weights=malloc(bytes);if(!weights) return 2;
        read_file(argv[1],names[part],weights,bytes);
        for(unsigned tile=0;tile<widths[part]/32;++tile) {
            qbs_descriptor_fields_t fields={.descriptor_version=QBS_DESCRIPTOR_VERSION,
                .weight_profile=part==1?QBS_WEIGHT_PROFILE_Q6_K:QBS_WEIGHT_PROFILE_Q4_K,
                .activation_profile=QBS_ACTIVATION_PROFILE_Q8_K,.weight_layout=QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
                .activation_layout=QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED,.n=32,.k_blocks=6};
            const qbs_descriptor_t descriptor={.header=qbs_pack_descriptor_header(&fields),.weight_base=0x20000000};
            float result[128];qbs_ref_result_t meta;
            const size_t tile_bytes=32*6*block[part];
            if(qbs_ref_execute(&descriptor,4,8,1024,0x30000000,
                (const unsigned char *)weights+tile*tile_bytes,tile_bytes,activation,sizeof(activation),
                result,128,NULL,NULL,&meta)!=QBS_REF_OK || meta.active_outputs!=128) return 2;
            for(unsigned row=0;row<4;++row)
                memcpy(output+offsets[part]+row*widths[part]+tile*32,result+row*32,32*sizeof(float));
            flags|=meta.fflags;++commands;
        }
        free(weights);
    }
    FILE *file=fopen(argv[2],"wb");
    if(!file || fwrite(output,1,sizeof(output),file)!=sizeof(output) || fclose(file)) return 2;
    printf("STAGE4_ORACLE commands=%u outputs=8192 flags=%u\n",commands,flags);
    return commands!=64 || flags!=1;
}
