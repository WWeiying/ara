/* Host-only independent multiply-accumulate model; never linked into an ELF. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <setjmp.h>
typedef uint8_t word;
static unsigned calls, mutation, injected;
static jmp_buf stop;
extern int macc_main(void);
unsigned long capacity(void) { return 512; }
long replay_write(long n, long fd, long p, long size) {
    if(n!=64 || fd!=1 || size<0) abort();
    return fwrite((const void *)p,1,(size_t)size,stdout);
}
static uint64_t hash(uint64_t h,const void *p,unsigned n) {
    const uint8_t *b=p;
    for(unsigned i=0;i<n;++i) h=(h^b[i])*UINT64_C(1099511628211);
    return h;
}
static unsigned selected(const uint8_t *m,unsigned i) { return (m[i/8]>>(i%8))&1; }
static unsigned long model(unsigned op,const word *a,const word *b,word *out,
                           unsigned long vl,unsigned long cap,const uint8_t *mask,
                           unsigned long start,unsigned long rm) {
#ifdef FULL_CAPTURE
    if(calls==482) longjmp(stop,1);
#endif
    if(op || cap!=512 || vl>cap || calls>=482 || rm) abort();
    if(out[-1]!=0x5b || out[cap]!=0x5b) abort();
    uint64_t before=hash(UINT64_C(14695981039346656037),a,cap);
    before=hash(before,b,cap); before=hash(before,mask,128);
    before=hash(before,out-1,cap+2);
    word old[512];
    for(unsigned i=0;i<cap;++i) old[i]=out[i];
    for(unsigned i=0;i<cap;++i)
        if(i>=start && i<vl && selected(mask,i))
            out[i]=(word)((unsigned)old[i]+(unsigned)a[i]*(unsigned)b[i]);
    uint64_t after=hash(UINT64_C(14695981039346656037),out-1,cap+2);
    if(!mutation) printf("CALL %u %u %lu %lu %lu %016llx %016llx\n",calls,op,vl,start,rm,
                        (unsigned long long)before,(unsigned long long)after);
    ++calls;
    if(!injected) {
        if((mutation>=1 && mutation<=4) || mutation==9) {
            for(unsigned i=0;i<cap;++i) {
                unsigned active=i>=start && i<vl && selected(mask,i);
                unsigned eligible=mutation==1 ? active :
                    mutation==2 ? start>0 && start<vl && i<start :
                    mutation==3 ? i>=start && i<vl && !selected(mask,i) :
                    mutation==4 ? start<vl && i>=vl : active && old[i]!=0;
                if(eligible) {
                    if(mutation==9) out[i]=(word)((unsigned)a[i]*(unsigned)b[i]);
                    else out[i]^=1;
                    injected=1; break;
                }
            }
        }
        if(mutation==5) { out[-1]^=1; injected=1; }
        if(mutation==6) { out[cap]^=1; injected=1; }
        if(mutation==7) { injected=1; return 1; }
        if(mutation==8) { injected=1; return UINT64_C(1)<<32; }
    }
    return 0;
}
#define OP(n) unsigned long op_##n(const word *a,const word *b,word *o,unsigned long v,unsigned long c,const uint8_t *m,unsigned long s,unsigned long r) { return model(n,a,b,o,v,c,m,s,r); }
OP(0) OP(1) OP(2) OP(3) OP(4) OP(5) OP(6) OP(7)
int main(int argc,char **argv) {
    mutation=argc>1 ? (unsigned)strtoul(argv[1],0,0):0;
    volatile int result=0;
    if(!setjmp(stop)) result=macc_main();
    printf("HOST_END calls=%u injected=%u result=%d\n",calls,injected,result);
    if(calls!=482 || (mutation && injected!=1)) return 98;
    return result;
}
