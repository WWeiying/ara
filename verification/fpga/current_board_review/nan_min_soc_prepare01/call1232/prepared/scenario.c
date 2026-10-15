#include <stdint.h>
#include "fp_reduction_inputs.h"
#if SEW == 16
typedef uint16_t word;
#elif SEW == 32
typedef uint32_t word;
#else
typedef uint64_t word;
#endif
struct fixture {uint64_t bits;unsigned flags;};
#include "fixtures.h"
#include "operations.h"
static word input[512],seed[64];
static uint8_t output[144] __attribute__((aligned(8))),mask[64];
extern unsigned long capacity(void);
typedef unsigned long (*operation)(const void *,const void *,void *,unsigned long,unsigned long,const void *,unsigned long,unsigned long);
static operation functions[]={FUNCTIONS};
static long syscall3(long n,long x,long y,long z){
    register long a0 __asm__("a0")=x,a1 __asm__("a1")=y,a2 __asm__("a2")=z,a7 __asm__("a7")=n;
    __asm__ volatile("ecall":"+r"(a0):"r"(a1),"r"(a2),"r"(a7):"memory");return a0;
}
static void text(const char *s){long n=0;while(s[n])++n;syscall3(64,1,(long)s,n);}
static void num(uint64_t n){char s[24];unsigned i=23;s[i]=0;do{s[--i]='0'+n%10;n/=10;}while(n);text(s+i);}
void probe_main(void){
    unsigned long vlenb;__asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
    unsigned cap=capacity(),errors=0,cases=0,flags_seen=0;
    if((vlenb!=64 && vlenb!=128) || cap!=(vlenb==64 ? CAP512:CAP1024)){
        text("RVV_FP_REDSPECIAL_CAPACITY_FAIL\n");syscall3(94,2,0,0);for(;;){}
    }
    const unsigned lengths[]={0,1,2,3,cap/2,cap-1,cap};
    for(unsigned scenario=0;scenario<8;++scenario){
        for(unsigned i=0;i<cap;++i)input[i]=reduction_input(scenario,i,SEW);
        for(unsigned i=0;i<64;++i)seed[i]=reduction_seed(scenario);
        unsigned index=0;
        for(unsigned l=0;l<7;++l)for(unsigned mode=0;mode<4;++mode)
        for(unsigned rm=0;rm<5;++rm)for(unsigned op=0;op<3;++op){
            struct fixture wanted=fixtures[vlenb==128][scenario*420+index++];
            for(unsigned i=0;i<64;++i)mask[i]=mode==0 ? 255:mode==1 ? 0:mode==2 ? 0x55:0x24;
            for(unsigned sticky=0;sticky<2;++sticky){
                if(!(scenario==1 && l==3 && mode==1 && rm==0 && op==1 && sticky==0))continue;
                for(unsigned i=0;i<144;++i)output[i]=0x5b;
                unsigned prior=errors,vl=lengths[l];
                unsigned long status=functions[op](input,seed,output+8,vl,cap,mask,rm,sticky);
                unsigned flags=status>>32;
                if((uint32_t)status || flags!=(wanted.flags|sticky))++errors;
                flags_seen|=flags;
                for(unsigned i=0;i<144;++i){
                    uint8_t byte=vl && i>=8 && i<8+SEW/8 ? wanted.bits>>((i-8)*8):0x5b;
                    if(output[i]!=byte)++errors;
                }
                if(errors!=prior && errors<20){text("RVV_FP_REDSPECIAL_DETAIL scenario=");num(scenario);
                    text(" op=");num(op);text(" vl=");num(vl);text(" mask=");num(mode);
                    text(" frm=");num(rm);text(" flags=");num(flags);text(" expected_flags=");num(wanted.flags|sticky);
                    text("\n");}
                ++cases;
            }
        }
    }
    text(errors ? "RVV_FP_REDSPECIAL_FAIL sew=":"RVV_FP_REDSPECIAL_PASS sew=");num(SEW);
    text(" cases=");num(cases);text(" flags_seen=");num(flags_seen);text(" errors=");num(errors);text("\n");
    syscall3(94,errors ? 1:0,0,0);for(;;){}
}
__asm__(".global _start\n_start:\n.option push\n.option norelax\nla gp,__global_pointer$\n.option pop\ntail probe_main\n");
