#include <stdint.h>
#include "operations.h"
#ifndef RESTART_INDEX_WIDTHS
#define RESTART_INDEX_WIDTHS 0
#endif
static uint8_t input[4096] __attribute__((aligned(8)));
static uint8_t output[4096] __attribute__((aligned(8))),wanted[4096],mask[128];
static uint8_t indices[8192] __attribute__((aligned(8)));
static const unsigned index_sews[]={INDEX_SEWS},modes[]={MODES};
extern unsigned long capacity(void);
typedef unsigned long (*operation)(const void *,void *,const void *,unsigned long,unsigned long,const void *,unsigned long);
static operation functions[]={FUNCTIONS};
static long syscall3(long n,long x,long y,long z){
    register long a0 __asm__("a0")=x,a1 __asm__("a1")=y,a2 __asm__("a2")=z,a7 __asm__("a7")=n;
    __asm__ volatile("ecall":"+r"(a0):"r"(a1),"r"(a2),"r"(a7):"memory");return a0;
}
static void text(const char *s){long n=0;while(s[n])++n;syscall3(64,1,(long)s,n);}
static void num(uint64_t n){char s[24];unsigned i=23;s[i]=0;do{s[--i]='0'+n%10;n/=10;}while(n);text(s+i);}
void probe_main(void){
    unsigned fullcap=capacity(),errors=0,cases=0;
    if(!fullcap || fullcap>1024 || fullcap*(SEW/8)>4032){
        text("RVV_INDEX_WIDTH_CAPACITY_FAIL\n");syscall3(94,2,0,0);for(;;){}}
    unsigned long max_start=0;
    if(RESTART_INDEX_WIDTHS){
        __asm__ volatile("csrr %0,vlenb":"=r"(max_start));
        max_start=max_start*8-1;
    }
    for(unsigned seed=0;seed<3;++seed){
        for(unsigned i=0;i<4096;++i)input[i]=(i*73+seed*19+(i>>3)*37)^0x85;
        for(unsigned op=0;op<OP_COUNT;++op){
            unsigned cap=fullcap,bytes=SEW/8,ib=index_sews[op]/8,mode=modes[op];
            if(ib==1 && cap>256/bytes)cap=256/bytes;
            unsigned lengths[]={0,1,2,3,cap/2,cap-1,cap};
            for(unsigned i=0;i<cap;++i){unsigned j=(i*5+3)%cap;if(mode==4)j/=2;
                uint64_t offset=j*bytes;for(unsigned b=0;b<ib;++b)indices[i*ib+b]=offset>>(8*b);}
            for(unsigned l=0;l<7;++l)for(unsigned predicate=0;predicate<4;++predicate)
            for(unsigned trial=0;trial<(RESTART_INDEX_WIDTHS ? 4U:1U);++trial){
                unsigned vl=lengths[l],start=0;
                if(RESTART_INDEX_WIDTHS)
                    start=trial==0 ? 1:trial==1 ? vl/2:trial==2 ? (vl<=max_start ? vl:cap-1):cap-1;
                for(unsigned i=0;i<128;++i)mask[i]=predicate==0 ? 255:predicate==1 ? 0:predicate==2 ? 0xaa:0x24;
                for(unsigned i=0;i<4096;++i)output[i]=wanted[i]=0x5b;
                for(unsigned i=start;i<vl;++i)if((mask[i/8]>>(i%8))&1){
                    unsigned j=(i*5+3)%cap;if(mode==4)j/=2;
                    for(unsigned b=0;b<bytes;++b){
                        unsigned a=64+i*bytes+b,z=64+j*bytes+b;
                        if(mode>=2)wanted[z]=input[a];else wanted[a]=input[z];
                    }
                }
                if(RESTART_INDEX_WIDTHS && !seed && !op && !predicate){
                    text("RVV_INDEX_WIDTH_TRIAL vl=");num(vl);text(" vstart=");num(start);text("\n");
                    syscall3(29,1,0x5409,1);
                }
                if(functions[op](input+64,output+64,indices,vl,cap,mask,start))++errors;
                for(unsigned i=0;i<4096;++i)if(output[i]!=wanted[i]){
                    if(errors<12){text("RVV_INDEX_WIDTH_DETAIL op=");num(op);text(" vl=");num(vl);
                        text(" mask=");num(predicate);text(" byte=");num(i);text(" expected=");num(wanted[i]);
                        if(RESTART_INDEX_WIDTHS){text(" vstart=");num(start);}
                        text(" actual=");num(output[i]);text("\n");}++errors;
                }
                ++cases;
            }
        }
    }
    text(errors ? "RVV_INDEX_WIDTH_FAIL sew=":"RVV_INDEX_WIDTH_PASS sew=");num(SEW);
    text(" cases=");num(cases);text(" errors=");num(errors);text("\n");
    syscall3(94,errors ? 1:0,0,0);for(;;){}
}
__asm__(".global _start\n_start:\n.option push\n.option norelax\nla gp,__global_pointer$\n.option pop\ntail probe_main\n");
