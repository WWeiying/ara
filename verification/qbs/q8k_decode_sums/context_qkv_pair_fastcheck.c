#include "integrity_words.h"
#define GGML_COMMON_DECL_C
#include "ggml-common.h"
#include "qbs/qbs.h"
#include <math.h>
#include <string.h>
#ifdef DECODE_LINUX
#include <stdio.h>
#else
#include "printf.h"
#endif

extern const float qkv_input[], q_expected[], k_expected[], v_expected[];
extern const unsigned char q_weights[], k_weights[], v_weights[];
extern void decode_original(const float *, void *, int64_t);
static block_q8_K packed[8] __attribute__((aligned(64)));
static float output[2080] __attribute__((aligned(64)));
static float reference[2048];
static unsigned long reference_fc, reference_vc;

static uint64_t cycles(void) {
#ifdef DECODE_LINUX
    static uint64_t ordinal;
    return ++ordinal;
#else
    uint64_t value;
    __asm__ volatile("fence rw,rw; rdcycle %0":"=r"(value)::"memory");
    return value;
#endif
}
static uint64_t hash(const void *data,size_t bytes) {
    if (bytes>=16384) return q8k_integrity_words(data,bytes);
    uint64_t h=UINT64_C(14695981039346656037);
    const unsigned char *p=data;
    for(size_t i=0;i<bytes;++i) h=(h^p[i])*UINT64_C(1099511628211);
    return h;
}
static qbs_status_t project(unsigned part,unsigned reuse,unsigned generation) {
    // Q, V, K retain their actual captured profiles and output dimensions.
    const unsigned n=part ? 256:1536;
    const unsigned char *w=part==0 ? q_weights:(part==1 ? v_weights:k_weights);
    const unsigned block_bytes=part==1 ? sizeof(block_q6_K):sizeof(block_q4_K);
    const unsigned offset=part==0 ? 0:(part==1 ? 1536:1792);
    for(unsigned row=0;row<n;row+=32) {
        qbs_descriptor_fields_t f={0};
        f.descriptor_version=QBS_DESCRIPTOR_VERSION;
        f.weight_profile=part==1 ? QBS_WEIGHT_PROFILE_Q6_K:QBS_WEIGHT_PROFILE_Q4_K;
        f.activation_profile=QBS_ACTIVATION_PROFILE_Q8_K;
        f.weight_layout=QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR;
        f.activation_layout=QBS_ACTIVATION_LAYOUT_ROW_MAJOR;
        f.n=32;f.k_blocks=6;f.context_id=0;
        f.context_generation=generation;
        const unsigned first=row==0 && (!reuse || part==0);
        const unsigned last=row+32==n && (!reuse || part==2);
        f.activation_access=first ? QBS_ACTIVATION_ACCESS_FILL:
            (last ? QBS_ACTIVATION_ACCESS_RELEASE:QBS_ACTIVATION_ACCESS_REUSE);
        const qbs_descriptor_t d={qbs_pack_descriptor_header(&f),(uintptr_t)(w+row*6*block_bytes)};
        qbs_status_t status=qbs_native_execute_command(0,&d,1,packed+1,output+16+offset+row,n,32,0);
        if(status!=QBS_STATUS_OK) return status;
    }
    return QBS_STATUS_OK;
}
int main(void) {
    unsigned errors=q8k_integrity_selftest();
    const uint64_t ih=hash(qkv_input,1536*4),qh=hash(q_weights,1536*6*sizeof(block_q4_K));
    const uint64_t kh=hash(k_weights,256*6*sizeof(block_q4_K)),vh=hash(v_weights,256*6*sizeof(block_q6_K));
    for(unsigned trial=0;trial<4;++trial) {
        const unsigned reuse=trial==1 || trial==2;
        memset(packed,0xa5,sizeof(packed));memset(output,0xa5,sizeof(output));
        __asm__ volatile("csrwi fcsr,0;csrwi vcsr,3;csrwi vstart,0":::"memory");
        uint64_t prep=0,execute=0,start=cycles();
        for(unsigned part=0;part<3;++part) {
            uint64_t a=cycles();
            if(!reuse || part==0) decode_original(qkv_input,packed+1,1536);
            uint64_t b=cycles();
            errors += project(part,reuse,trial*3+(reuse ? 1:part+1))!=QBS_STATUS_OK;
            uint64_t c=cycles();prep+=b-a;execute+=c-b;
        }
        uint64_t end=cycles();unsigned long fc,vc;
        __asm__ volatile("frcsr %0;csrr %1,vcsr":"=r"(fc),"=r"(vc)::"memory");
        for(unsigned i=0;i<2048;++i) {
            float want=i<1536 ? q_expected[i]:(i<1792 ? v_expected[i-1536]:k_expected[i-1792]);
            float got=output[16+i];
            errors += !isfinite(got)||!isfinite(want)||fabsf(got-want)>2e-3f+2e-3f*fabsf(want);
        }
        if(!trial) {memcpy(reference,output+16,sizeof(reference));reference_fc=fc;reference_vc=vc;}
        errors += memcmp(reference,output+16,sizeof(reference))!=0||reference_fc!=fc||reference_vc!=vc;
        for(unsigned g=0;g<2;++g) {
            const unsigned char *p=(const unsigned char *)&packed[g ? 7:0];
            for(unsigned i=0;i<sizeof(packed[0]);++i) errors+=p[i]!=0xa5;
            p=(const unsigned char *)&output[g ? 2064:0];
            for(unsigned i=0;i<64;++i) errors+=p[i]!=0xa5;
        }
        errors += hash(qkv_input,1536*4)!=ih||hash(q_weights,1536*6*sizeof(block_q4_K))!=qh||
            hash(k_weights,256*6*sizeof(block_q4_K))!=kh||hash(v_weights,256*6*sizeof(block_q6_K))!=vh;
        printf("CONTEXT_QKV trial=%u reuse=%u prep=%lu execute=%lu total=%lu fcsr=%lu vcsr=%lu digest=%016lx\n",
               trial,reuse,(unsigned long)prep,(unsigned long)execute,(unsigned long)(end-start),fc,vc,
               (unsigned long)hash(output+16,sizeof(reference)));
    }
    printf("CONTEXT_QKV_RESULT errors=%u trials=4 k=1536 outputs=2048 commands=256\n",errors);
    return errors ? 1:0;
}
