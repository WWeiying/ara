#include <stdint.h>
#include "operations.h"
#include "input_bits.h"
#ifndef SMALL_SEW
#define SMALL_SEW 32
#endif
struct fixture{uint64_t bits;unsigned flags;};
#include "fixtures.h"
static uint8_t input[8192] __attribute__((aligned(8)));
static uint8_t output[8208] __attribute__((aligned(8))),wanted[8208],mask[128];
extern unsigned long capacity(void);
typedef unsigned long (*operation)(const void *,void *,const void *,unsigned long,unsigned long,unsigned long,unsigned long);
static operation functions[]={FUNCTIONS};
static long syscall3(long n,long x,long y,long z){
    register long a0 __asm__("a0")=x,a1 __asm__("a1")=y,a2 __asm__("a2")=z,a7 __asm__("a7")=n;
    __asm__ volatile("ecall":"+r"(a0):"r"(a1),"r"(a2),"r"(a7):"memory");return a0;
}
static void text(const char *s){long n=0;while(s[n])++n;syscall3(64,1,(long)s,n);}
static void num(uint64_t n){char s[24];unsigned i=23;s[i]=0;do{s[--i]='0'+n%10;n/=10;}while(n);text(s+i);}
static void word(uint8_t *p,unsigned bytes,uint64_t x){for(unsigned b=0;b<bytes;++b)p[b]=x>>(8*b);}
void probe_main(void){
    unsigned cap=capacity(),errors=0,cases=0,flags_seen=0;
    if(!cap || cap>1024){text("RVV_FP_WIDTH_CAPACITY_FAIL\n");syscall3(94,2,0,0);for(;;){}}
    unsigned lengths[]={0,1,2,3,cap/2,cap-1,cap};
    for(unsigned seed=0;seed<3;++seed)for(unsigned op=0;op<3;++op)
    for(unsigned rm=0;rm<5;++rm)for(unsigned l=0;l<7;++l)for(unsigned mode=0;mode<4;++mode){
        unsigned vl=lengths[l],src=(op ? 2:1)*(SMALL_SEW/8),dst=(op ? 1:2)*(SMALL_SEW/8),flags=seed==2 ? 1:0;
        for(unsigned i=0;i<128;++i)mask[i]=mode==0 ? 255:mode==1 ? 0:mode==2 ? 0xaa:0x24;
        for(unsigned i=0;i<8208;++i)output[i]=wanted[i]=0x5b;
        for(unsigned i=0;i<cap;++i){unsigned k=(i+seed*11)%32;
            word(input+i*src,src,input_bits[op ? 1:0][k%16]);
            if(i<vl && ((mask[i/8]>>(i%8))&1)){
                word(wanted+8+i*dst,dst,expected[rm][op][k].bits);flags|=expected[rm][op][k].flags;
            }
        }
        unsigned long result=functions[op](input,output+8,mask,vl,cap,rm,seed==2 ? 1:0);
        if((uint32_t)result || result>>32!=flags)++errors;
        for(unsigned i=0;i<8208;++i)if(output[i]!=wanted[i])++errors;
        flags_seen|=flags;++cases;
    }
    text(errors ? "RVV_FP_WIDTH_FAIL cases=":"RVV_FP_WIDTH_PASS cases=");num(cases);
    text(" errors=");num(errors);text(" flags_seen=");num(flags_seen);text("\n");
    syscall3(94,errors ? 1:0,0,0);for(;;){}
}
__asm__(".global _start\n_start:\n.option push\n.option norelax\nla gp,__global_pointer$\n.option pop\ntail probe_main\n");
