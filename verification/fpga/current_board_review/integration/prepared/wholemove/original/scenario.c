#include <stdint.h>
#include "operations.h"
static uint8_t input[1024] __attribute__((aligned(64)));
static uint8_t output[1088] __attribute__((aligned(64)));
typedef unsigned long (*operation)(const void *,void *,unsigned long,unsigned long);
static operation functions[]={FUNCTIONS};
static long syscall3(long n,long x,long y,long z){
    register long a0 __asm__("a0")=x,a1 __asm__("a1")=y,a2 __asm__("a2")=z,a7 __asm__("a7")=n;
    __asm__ volatile("ecall":"+r"(a0):"r"(a1),"r"(a2),"r"(a7):"memory");return a0;
}
static void text(const char *s){long n=0;while(s[n])++n;syscall3(64,1,(long)s,n);}
static void num(uint64_t n){char s[24];unsigned i=23;s[i]=0;do{s[--i]='0'+n%10;n/=10;}while(n);text(s+i);}
void probe_main(void){
    unsigned long vlenb;__asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
    unsigned errors=0,cases=0,skips=0;
    if(vlenb<32 || vlenb>128){text("RVV_WHOLE_CAPACITY_FAIL\n");syscall3(94,2,0,0);for(;;){}}
    { unsigned seed=0,op=16,mode=1;
        unsigned n=op<16 ? 1u<<(op/4):1u<<(op-16);
        unsigned bytes=op<16 ? 1u<<(op%4):1u<<mode;
        if(mode==4 && op>=16)bytes=1;
        unsigned evl=n*vlenb/bytes;
        unsigned starts[]={0,1,evl/2,evl,evl+1};
        unsigned prior=errors;
        for(unsigned st=1;st<2;++st){
            unsigned start=starts[st];
            if(start>evl || start>=8*vlenb || (mode==4 && op>=16)){++skips;continue;}
            for(unsigned i=0;i<1024;++i)input[i]=(uint8_t)(i*37+seed*71+3);
            for(unsigned i=0;i<1088;++i)output[i]=0x5b;
            unsigned long status=functions[op](input,output+32,start,mode);
            if((uint32_t)status || status>>32!=start)++errors;
            for(unsigned i=0;i<1088;++i){unsigned active=i>=32+start*bytes && i<32+n*vlenb;
                uint8_t wanted=active ? input[i-32]:0x5b;
                if(output[i]!=wanted){
#if DETAIL_BYTES
                    if(errors<12){text("RVV_WHOLE_BYTE op=");num(op);text(" mode=");num(mode);
                        text(" vstart=");num(start);text(" byte=");num(i);text(" expected=");num(wanted);
                        text(" actual=");num(output[i]);text("\n");}
#endif
                    ++errors;
                }}
            ++cases;
        }
        if(errors!=prior){text("RVV_WHOLE_DETAIL op=");num(op);text(" mode=");num(mode);text(" errors=");num(errors-prior);text("\n");}
    }
    text(errors ? "RVV_WHOLE_FAIL cases=":"RVV_WHOLE_PASS cases=");num(cases);text(" skips=");num(skips);text(" errors=");num(errors);text("\n");
    syscall3(94,errors ? 1:0,0,0);for(;;){}
}
__asm__(".global _start\n_start:\n.option push\n.option norelax\nla gp,__global_pointer$\n.option pop\ntail probe_main\n");
