#ifndef Q8K_INTEGRITY_WORDS_H
#define Q8K_INTEGRITY_WORDS_H
#include <riscv_vector.h>
#include <stdint.h>
#include <stddef.h>

// Non-cryptographic immutable-buffer check, outside every measured region.
// Host SHA256 pins and captured numerical oracles remain independent checks.
static uint64_t q8k_integrity_words(const void *data,size_t bytes) {
    const uint64_t *words=(const uint64_t *)data;
    const size_t maximum=__riscv_vsetvlmax_e64m1();
    vuint64m1_t sum=__riscv_vmv_v_x_u64m1(0,maximum);
    vuint64m1_t weighted=__riscv_vmv_v_x_u64m1(0,maximum);
    for(size_t i=0;i<bytes/8;) {
        size_t vl=__riscv_vsetvl_e64m1(bytes/8-i);
        vuint64m1_t value=__riscv_vle64_v_u64m1(words+i,vl);
        vuint64m1_t index=__riscv_vid_v_u64m1(vl);
        index=__riscv_vadd_vx_u64m1(index,i,vl);
        index=__riscv_vsll_vx_u64m1(index,1,vl);
        index=__riscv_vadd_vx_u64m1(index,1,vl);
        sum=__riscv_vadd_vv_u64m1_tu(sum,sum,value,vl);
        value=__riscv_vmul_vv_u64m1(value,index,vl);
        weighted=__riscv_vadd_vv_u64m1_tu(weighted,weighted,value,vl);
        i+=vl;
    }
    vuint64m1_t zero=__riscv_vmv_v_x_u64m1(0,maximum);
    uint64_t a=__riscv_vmv_x_s_u64m1_u64(__riscv_vredsum_vs_u64m1_u64m1(sum,zero,maximum));
    uint64_t b=__riscv_vmv_x_s_u64m1_u64(__riscv_vredsum_vs_u64m1_u64m1(weighted,zero,maximum));
    uint64_t result=b^((a<<17)|(a>>47))^bytes;
    const unsigned char *p=(const unsigned char *)data;
    for(size_t i=bytes/8*8;i<bytes;++i) result=(result^p[i])*UINT64_C(1099511628211);
    return result;
}
static unsigned q8k_integrity_selftest(void) {
    uint64_t data[37] __attribute__((aligned(64)));
    const size_t lengths[]={0,1,7,8,9,127,128,129,255,256,257,sizeof(data)};
    unsigned errors=0;
    for(size_t i=0;i<37;++i) data[i]=(UINT64_C(0xfedcba9876543210)+i)*(i+7);
    for(size_t t=0;t<sizeof(lengths)/sizeof(lengths[0]);++t) {
        size_t n=lengths[t];uint64_t a=0,b=0;
        for(size_t i=0;i<n/8;++i) {a+=data[i];b+=data[i]*(2*i+1);}
        uint64_t expected=b^((a<<17)|(a>>47))^n;
        const unsigned char *p=(const unsigned char *)data;
        for(size_t i=n/8*8;i<n;++i) expected=(expected^p[i])*UINT64_C(1099511628211);
        errors+=q8k_integrity_words(data,n)!=expected;
    }
    return errors;
}
#endif
