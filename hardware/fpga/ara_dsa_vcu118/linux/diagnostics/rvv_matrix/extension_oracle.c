#include <stdint.h>
#include "operations.h"
#ifndef EXTENSION_OP_MASK
#define EXTENSION_OP_MASK 15U
#endif
static uint8_t input[1024],output[1026],expected[1024],mask[128];
extern unsigned long capacity(void);
typedef unsigned long (*operation)(const void *,void *,const void *,unsigned long,unsigned long);
static operation functions[]={FUNCTIONS};
static long syscall3(long n,long x,long y,long z){
    register long a0 __asm__("a0")=x,a1 __asm__("a1")=y,a2 __asm__("a2")=z,a7 __asm__("a7")=n;
    __asm__ volatile("ecall":"+r"(a0):"r"(a1),"r"(a2),"r"(a7):"memory");return a0;
}
static void text(const char *s){long n=0;while(s[n])++n;syscall3(64,1,(long)s,n);}
static void num(uint64_t n){char s[24];unsigned i=23;s[i]=0;do{s[--i]='0'+n%10;n/=10;}while(n);text(s+i);}
static uint64_t load_word(const uint8_t *p,unsigned bytes){
    uint64_t x=0;for(unsigned b=0;b<bytes;++b)x|=(uint64_t)p[b]<<(8*b);return x;
}
static void store_word(uint8_t *p,unsigned bytes,uint64_t x){
    for(unsigned b=0;b<bytes;++b)p[b]=x>>(8*b);
}
void probe_main(void){
    unsigned cap=capacity(),errors=0,cases=0;unsigned long vlenb;
    __asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
    unsigned bytes=DEST_REGS*vlenb;
#ifdef NARROW_SUITE
    unsigned source_bytes=2*SEW/8;
#else
    unsigned source_bytes=SEW/FACTOR/8;
#endif
    if(!cap || bytes>1024 || cap*source_bytes>1024){text("RVV_EXTENSION_CAPACITY_FAIL\n");syscall3(94,2,0,0);for(;;){}}
    unsigned lengths[]={0,1,2,3,cap/2,cap-1,cap};
    for(unsigned seed=0;seed<3;++seed){
        for(unsigned i=0;i<cap*source_bytes;++i)input[i]=(i*73+seed*19)^0x85;
        for(unsigned op=0;op<OP_COUNT;++op)for(unsigned l=0;l<7;++l)for(unsigned mode=0;mode<4;++mode){
            if(!(EXTENSION_OP_MASK & (1U<<op)))continue;
            unsigned vl=lengths[l];
            for(unsigned i=0;i<128;++i)mask[i]=mode==0 ? 255:mode==1 ? 0:mode==2 ? 0xaa:0x24;
            for(unsigned i=0;i<1026;++i)output[i]=0x5b;
            for(unsigned i=0;i<bytes;++i)expected[i]=0x5b;
#ifdef NARROW_SUITE
            for(unsigned i=0;i<cap*source_bytes;++i)expected[i]=input[i];
#else
            if(op>=2){unsigned offset=(DEST_REGS-SOURCE_REGS)*vlenb;
                for(unsigned i=0;i<cap*source_bytes;++i)expected[offset+i]=input[i];}
#endif
            for(unsigned i=0;i<vl;++i)if((mask[i/8]>>(i%8))&1){
                uint64_t x=load_word(input+i*source_bytes,source_bytes);
#ifdef NARROW_SUITE
                if(op%2){uint64_t sign=UINT64_C(1)<<(2*SEW-1);x=(uint64_t)((int64_t)((x^sign)-sign)>>3);}
                else x>>=3;
#else
                if(op%2){uint64_t sign=UINT64_C(1)<<(SEW/FACTOR-1);x=(uint64_t)(int64_t)((x^sign)-sign);}
#endif
                store_word(expected+i*(SEW/8),SEW/8,x);
            }
            if(functions[op](input,output+1,mask,vl,cap))++errors;
            for(unsigned i=0;i<bytes;++i)if(output[i+1]!=expected[i])++errors;
            if(output[0]!=0x5b || output[bytes+1]!=0x5b)++errors;
            ++cases;
        }
    }
#ifdef NARROW_SUITE
    text(errors ? "RVV_NARROW_ALIAS_FAIL sew=":"RVV_NARROW_ALIAS_PASS sew=");
#else
    text(errors ? "RVV_EXTENSION_FAIL sew=":"RVV_EXTENSION_PASS sew=");
#endif
    num(SEW);
    text(" cases=");num(cases);text(" errors=");num(errors);text("\n");
    syscall3(94,errors ? 1:0,0,0);for(;;){}
}
__asm__(".global _start\n_start:\n.option push\n.option norelax\nla gp,__global_pointer$\n.option pop\ntail probe_main\n");
