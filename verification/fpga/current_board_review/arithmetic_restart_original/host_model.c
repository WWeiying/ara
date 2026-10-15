/* Scalar host model only. This file is never linked into a vector ELF. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <setjmp.h>
#if SEW == 8
typedef uint8_t word;
#elif SEW == 16
typedef uint16_t word;
#endif
static unsigned calls, mutation, injected;
static jmp_buf stop;
extern int arithmetic_main(void);
unsigned long capacity(void) { return CAP; }
long replay_write(long n, long fd, long p, long length) {
    if(n!=64 || fd!=1 || length<0) abort();
    return fwrite((const void *)p, 1, (size_t)length, stdout);
}
static uint64_t hash(uint64_t h, const void *p, unsigned n) {
    const uint8_t *b=p;
    for(unsigned i=0;i<n;++i) h=(h^b[i])*UINT64_C(1099511628211);
    return h;
}
static unsigned selected(const uint8_t *m, unsigned i) { return (m[i/8]>>(i%8))&1; }
static unsigned long model(unsigned op, const word *a, const word *b, word *out,
                           unsigned long vl, unsigned long cap, const uint8_t *mask,
                           unsigned long start) {
#ifdef FULL_CAPTURE
    if(calls==COUNT) longjmp(stop,1);
#endif
    if(op || cap!=CAP || vl>cap || calls>=COUNT) abort();
    for(unsigned i=0;i<cap+2;++i) if(out[(long)i-1]!=(word)0x5b) abort();
    uint64_t h=hash(UINT64_C(14695981039346656037),a,cap*sizeof(word));
    h=hash(h,b,cap*sizeof(word)); h=hash(h,mask,128);
    h=hash(h,out-1,(cap+2)*sizeof(word));
    if(!mutation) printf("CALL %u %u %lu %lu %016llx\n",calls,op,vl,start,(unsigned long long)h);
    for(unsigned i=0;i<cap;++i)
        if(i>=start && i<vl && selected(mask,i)) out[i]=(word)((uint64_t)a[i]+b[i]);
    ++calls;
    if(!injected) {
        if(mutation>=1 && mutation<=4) {
            for(unsigned i=0;i<cap;++i) {
                unsigned eligible=mutation==1 ? i>=start && i<vl && selected(mask,i) :
                                  mutation==2 ? start>0 && start<vl && i<start :
                                  mutation==3 ? i>=start && i<vl && !selected(mask,i) :
                                                start<vl && i>=vl;
                if(eligible) { out[i]^=1; injected=1; break; }
            }
        }
        if(mutation==5) { out[-1]^=1; injected=1; }
        if(mutation==6) { out[cap]^=1; injected=1; }
        if(mutation==7) { injected=1; return 1; }
        if(mutation==8) { injected=1; return UINT64_C(1)<<32; }
    }
    return 0;
}
#define OP(n) unsigned long op_##n(const word *a,const word *b,word *o,unsigned long v,unsigned long c,const uint8_t *m,unsigned long s) { return model(n,a,b,o,v,c,m,s); }
OP(0) OP(1) OP(2) OP(3) OP(4) OP(5) OP(6) OP(7) OP(8)
OP(9) OP(10) OP(11) OP(12) OP(13) OP(14) OP(15) OP(16)
OP(17) OP(18) OP(19) OP(20) OP(21) OP(22) OP(23) OP(24)
int main(int argc,char **argv) {
    mutation=argc>1 ? (unsigned)strtoul(argv[1],0,0):0;
    volatile int result=0;
    if(!setjmp(stop)) result=arithmetic_main();
    printf("HOST_END calls=%u injected=%u result=%d\n",calls,injected,result);
    if(calls!=COUNT || (mutation && injected!=1)) return 98;
    return result;
}
