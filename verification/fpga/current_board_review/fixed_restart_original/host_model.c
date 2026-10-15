/* Independent e8 scalar model for source/oracle validation; never a DUT input. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <setjmp.h>
static unsigned calls, mutation, injected;
static jmp_buf stop;
extern int fixed_main(void);
unsigned long capacity(void) { return 512; }
long replay_write(long n, long fd, long p, long length) {
    if(n!=64 || fd!=1 || length<0) abort();
    return fwrite((const void *)p,1,(size_t)length,stdout);
}
static uint64_t hash(uint64_t h,const void *p,unsigned n) {
    const uint8_t *b=p;
    for(unsigned i=0;i<n;++i) h=(h^b[i])*UINT64_C(1099511628211);
    return h;
}
static unsigned selected(const uint8_t *m,unsigned i) { return (m[i/8]>>(i%8))&1; }
static uint8_t fractional(uint8_t a,uint8_t b,unsigned rm,unsigned *sat) {
    int x=a<128 ? a:(int)a-256, y=b<128 ? b:(int)b-256;
    int product=x*y;
    int quotient=product>=0 ? product/128:-((-product+127)/128);
    unsigned remainder=(unsigned)(product-quotient*128);
    if(rm==0) quotient+=remainder>=64;
    else if(rm==1) quotient+=remainder>64 || (remainder==64 && (quotient&1));
    else if(rm==3) quotient+=remainder!=0 && !(quotient&1);
    if(quotient>127) { quotient=127; *sat=1; }
    return (uint8_t)quotient;
}
static unsigned long model(unsigned op,const uint8_t *a,const uint8_t *b,uint8_t *out,
                           unsigned long vl,unsigned long cap,const uint8_t *mask,
                           unsigned long start,unsigned long control) {
#ifdef FULL_CAPTURE
    if(calls==777) longjmp(stop,1);
#endif
    if(op || cap!=512 || vl>cap || calls>=777 || control>=8) abort();
    for(unsigned i=0;i<cap+2;++i) if(out[(long)i-1]!=0x5b) abort();
    uint64_t h=hash(UINT64_C(14695981039346656037),a,cap);
    h=hash(h,b,cap); h=hash(h,mask,128); h=hash(h,out-1,cap+2);
    if(!mutation) printf("CALL %u %u %lu %lu %lu %016llx\n",calls,op,vl,start,control,(unsigned long long)h);
    unsigned sat=control>>2;
    for(unsigned i=0;i<cap;++i)
        if(i>=start && i<vl && selected(mask,i)) out[i]=fractional(a[i],b[i],control&3,&sat);
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
        if(mutation==7) { injected=1; return ((uint64_t)sat<<32)|1; }
        if(mutation==8 && sat) { injected=1; sat=0; }
        if(mutation==9 && !sat) { injected=1; sat=1; }
    }
    return (uint64_t)sat<<32;
}
#define OP(n) unsigned long op_##n(const uint8_t *a,const uint8_t *b,uint8_t *o,unsigned long v,unsigned long c,const uint8_t *m,unsigned long s,unsigned long rm) { return model(n,a,b,o,v,c,m,s,rm); }
OP(0) OP(1) OP(2) OP(3)
int main(int argc,char **argv) {
    mutation=argc>1 ? (unsigned)strtoul(argv[1],0,0):0;
    volatile int result=0;
    if(!setjmp(stop)) result=fixed_main();
    printf("HOST_END calls=%u injected=%u result=%d\n",calls,injected,result);
    if(calls!=777 || (mutation && injected!=1)) return 98;
    return result;
}
