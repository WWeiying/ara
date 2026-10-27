#include "integrity_words.h"
#define GGML_COMMON_DECL_C
#include "ggml-common.h"
#include <math.h>
#include <string.h>
#include "qbs/qbs.h"
#ifdef DECODE_LINUX
#include <stdio.h>
#else
#include "printf.h"
#endif

extern const float projection_input[], projection_expected[];
extern const unsigned char projection_weights[];
extern void decode_original(const float *, void *, int64_t);
extern void decode_candidate(const float *, void *, int64_t);
static block_q8_K packed[8] __attribute__((aligned(64)));
static block_q8_K original_packed[6];
static float output[1568] __attribute__((aligned(64)));
static uint64_t first_hash;
static unsigned first_fcsr, first_vcsr;

static uint64_t cycles(void) {
#ifdef DECODE_LINUX
    static uint64_t ordinal;
    return ++ordinal;
#else
    uint64_t value;
    __asm__ volatile("fence rw,rw; rdcycle %0" : "=r"(value) :: "memory");
    return value;
#endif
}

static uint64_t hash_bytes(const void *data, size_t count) {
    if (count>=16384) return q8k_integrity_words(data,count);
    const unsigned char *p = data;
    uint64_t value = UINT64_C(14695981039346656037);
    for (size_t i=0;i<count;++i) value=(value ^ p[i])*UINT64_C(1099511628211);
    return value;
}

static qbs_status_t project(unsigned generation) {
    for (unsigned row=0;row<1536;row+=32) {
        qbs_descriptor_fields_t f = {0};
        f.descriptor_version=QBS_DESCRIPTOR_VERSION;
        f.weight_profile=QBS_WEIGHT_PROFILE_Q4_K;
        f.activation_profile=QBS_ACTIVATION_PROFILE_Q8_K;
        f.weight_layout=QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR;
        f.activation_layout=QBS_ACTIVATION_LAYOUT_ROW_MAJOR;
        f.n=32; f.k_blocks=6; f.context_id=0; f.context_generation=generation;
        f.activation_access=row==0 ? QBS_ACTIVATION_ACCESS_FILL :
            (row==1504 ? QBS_ACTIVATION_ACCESS_RELEASE : QBS_ACTIVATION_ACCESS_REUSE);
        const qbs_descriptor_t d={qbs_pack_descriptor_header(&f),
                                 (uintptr_t)(projection_weights+row*6*144)};
        qbs_status_t status=qbs_native_execute_command(0,&d,1,packed+1,output+16+row,1536,32,0);
        if (status!=QBS_STATUS_OK) return status;
    }
    return QBS_STATUS_OK;
}

int main(void) {
    unsigned errors=q8k_integrity_selftest();
    const uint64_t input_hash=hash_bytes(projection_input,1536*4);
    const uint64_t weight_hash=hash_bytes(projection_weights,1536*6*144);
    for (unsigned trial=0;trial<4;++trial) {
        const unsigned candidate=trial==1 || trial==2;
        memset(packed,0xa5,sizeof(packed)); memset(output,0xa5,sizeof(output));
        __asm__ volatile("csrwi fcsr,0; csrwi vcsr,3; csrwi vstart,0" ::: "memory");
        const uint64_t start=cycles();
        if (candidate) decode_candidate(projection_input,packed+1,1536);
        else decode_original(projection_input,packed+1,1536);
        const uint64_t middle=cycles();
        qbs_status_t status=project(trial+1);
        const uint64_t end=cycles();
        unsigned long fc,vc;
        __asm__ volatile("frcsr %0; csrr %1,vcsr" : "=r"(fc),"=r"(vc) :: "memory");
        errors += status!=QBS_STATUS_OK;
        if (!trial) memcpy(original_packed,packed+1,sizeof(original_packed));
        errors += memcmp(original_packed,packed+1,sizeof(original_packed))!=0;
        for (unsigned i=0;i<1536;++i) {
            float got=output[16+i], ref=projection_expected[i];
            errors += !isfinite(got) || !isfinite(ref) || fabsf(got-ref)>2e-3f+2e-3f*fabsf(ref);
        }
        for (unsigned g=0;g<2;++g) {
            const unsigned char *p=(const unsigned char *)&packed[g?7:0];
            for (unsigned i=0;i<sizeof(packed[0]);++i) errors += p[i]!=0xa5;
            p=(const unsigned char *)&output[g?1552:0];
            for (unsigned i=0;i<64;++i) errors += p[i]!=0xa5;
        }
        uint64_t hash=hash_bytes(output+16,1536*4);
        if (!trial) { first_hash=hash; first_fcsr=fc; first_vcsr=vc; }
        errors += hash!=first_hash || fc!=first_fcsr || vc!=first_vcsr;
        errors += input_hash!=hash_bytes(projection_input,1536*4) ||
                  weight_hash!=hash_bytes(projection_weights,1536*6*144);
        printf("DECODE_PROJECTION trial=%u candidate=%u prep=%lu execute=%lu total=%lu fcsr=%lu vcsr=%lu digest=%016lx\n",
               trial,candidate,(unsigned long)(middle-start),(unsigned long)(end-middle),
               (unsigned long)(end-start),fc,vc,(unsigned long)hash);
    }
    printf("DECODE_PROJECTION_RESULT errors=%u trials=4 m=1 n=1536 k=1536 commands=192\n",errors);
    return errors?1:0;
}
