#ifndef Q8K_INTEGRITY_EQUAL_H
#define Q8K_INTEGRITY_EQUAL_H
#include <riscv_vector.h>
#include <stdint.h>
#include <stddef.h>

// Exact byte comparison, outside all timing windows. No checksum arithmetic.
static unsigned q8k_integrity_equal(const void *left,const void *right,size_t bytes) {
    const unsigned char *a=left,*b=right;
    for(size_t i=0;i<bytes;) {
        size_t vl=__riscv_vsetvl_e8m8(bytes-i);
        vuint8m8_t x=__riscv_vle8_v_u8m8(a+i,vl);
        vuint8m8_t y=__riscv_vle8_v_u8m8(b+i,vl);
        vbool1_t different=__riscv_vmsne_vv_u8m8_b1(x,y,vl);
        if(__riscv_vfirst_m_b1(different,vl)>=0) return 0;
        i+=vl;
    }
    return 1;
}
static unsigned q8k_integrity_equal_selftest(void) {
    unsigned char a[1041],b[1041];
    const size_t lengths[]={0,1,15,16,17,127,128,129,1023,1024,1025,1041};
    unsigned errors=0;
    for(size_t i=0;i<sizeof(a);++i) a[i]=b[i]=(unsigned char)(i*17+3);
    for(size_t t=0;t<sizeof(lengths)/sizeof(lengths[0]);++t) {
        size_t n=lengths[t];errors+=!q8k_integrity_equal(a,b,n);
        if(n) {
            const size_t points[]={0,n/2,n-1};
            for(size_t j=0;j<3;++j) {
                b[points[j]]^=1;
                errors+=q8k_integrity_equal(a,b,n);
                b[points[j]]^=1;
            }
        }
    }
    return errors;
}
#endif
