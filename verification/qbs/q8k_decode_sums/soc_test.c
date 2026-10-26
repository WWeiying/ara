#include "quantizers.h"
#include "captures.h"
#ifdef DECODE_LINUX
#include <stdio.h>
#else
#include "printf.h"
#endif

static float input[8960] __attribute__((aligned(64)));
static block_q8_K output[37] __attribute__((aligned(64)));
static block_q8_K reference[37];
static uint64_t hash(const void *p, size_t n) {
    const unsigned char *b=p;
    uint64_t h=UINT64_C(14695981039346656037);
    for (size_t i=0;i<n;++i) h=(h^b[i])*UINT64_C(1099511628211);
    return h;
}
static uint64_t cycle(void) {
#ifdef DECODE_LINUX
    // The Linux golden has no timing meaning; user cycle CSR access is disabled.
    static uint64_t ordinal;
    return ++ordinal;
#else
    uint64_t value;
    asm volatile("fence rw,rw; rdcycle %0" : "=r"(value) :: "memory");
    return value;
#endif
}
int main(void) {
    unsigned errors=0;
    for (unsigned c=0;c<2;++c) {
        const unsigned index=c?6:0;
        const unsigned k=capture_lengths[index];
        memcpy(input,capture_data[index],k*4);
        uint64_t elapsed[4], digests[4];
        unsigned flags[4], vcsr[4];
        for (unsigned t=0;t<4;++t) {
            memset(output,0xa5,sizeof(output));
            asm volatile("csrwi fcsr,0; csrwi vcsr,5" ::: "memory");
            const uint64_t begin=cycle();
            if (t==1 || t==2) decode_candidate(input,output+1,k);
            else decode_original(input,output+1,k);
            asm volatile("frcsr %0" : "=r"(flags[t]) :: "memory");
            elapsed[t]=cycle()-begin;
            asm volatile("csrr %0,vcsr" : "=r"(vcsr[t]) :: "memory");
            if (!t) memcpy(reference,output,sizeof(output));
            else errors+=memcmp(reference,output,sizeof(output))!=0;
            errors+=memcmp(input,capture_data[index],k*4)!=0;
            for (unsigned b=0;b<37;++b) {
                if (b>=1 && b<=k/256) continue;
                const unsigned char *p=(const unsigned char *)&output[b];
                for (size_t j=0;j<sizeof(output[0]);++j) errors+=p[j]!=0xa5;
            }
            for (unsigned b=1;b<=k/256;++b) {
                for (unsigned g=0;g<16;++g) {
                    int sum=0;
                    for (unsigned j=0;j<16;++j) sum+=output[b].qs[g*16+j];
                    errors+=sum!=output[b].bsums[g];
                }
            }
            digests[t]=hash(output+1,k/256*sizeof(output[0]));
            errors+=flags[t]!=flags[0] || vcsr[t]!=vcsr[0];
        }
        for (unsigned t=0;t<4;++t)
            printf("DECODE_SUMS k=%u trial=%u candidate=%u cycles=%lu fcsr=%u vcsr=%u digest=%016lx\n",
                   k,t,(unsigned)(t==1||t==2),(unsigned long)elapsed[t],flags[t],vcsr[t],(unsigned long)digests[t]);
    }
    printf("DECODE_SUMS_RESULT errors=%u trials=8\n",errors);
    return errors?1:0;
}
