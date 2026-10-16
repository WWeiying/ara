#include <stdint.h>
#include "operations.h"
#if SEW == 16
typedef uint16_t word;
#elif SEW == 32
typedef uint32_t word;
#else
typedef uint64_t word;
#endif
struct fixture{word bits;unsigned flags;};
#include "fixtures.h"
static word a[1024],b[1024],output[1026];
static uint8_t mask[128];
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
#if SCALAR_FORMS
    static const unsigned scalar_indices[]={SCALAR_INDICES};
#endif
    unsigned cap=capacity(),errors=0,cases=0,flags_seen=0;
    if(!cap || cap>1024){text("RVV_FP_CAPACITY_FAIL\n");syscall3(94,2,0,0);for(;;){}}
    unsigned lengths[]={0,1,2,3,cap/2,cap-1,cap};
    for(unsigned seed=0;seed<(SCALAR_FORMS ? SCALAR_SEEDS:3);++seed)for(unsigned op=0;op<OP_COUNT;++op){
        unsigned prior=errors;
        for(unsigned rm=0;rm<5;++rm)for(unsigned l=0;l<7;++l)for(unsigned mode=0;mode<4;++mode){
            unsigned vl=lengths[l],flags=seed==2 ? 1:0;
            for(unsigned i=0;i<128;++i)mask[i]=mode==0 ? 255:mode==1 ? 0:mode==2 ? 0xaa:0x24;
            for(unsigned i=0;i<cap;++i){unsigned k=(i+seed*11)%32;
                a[i]=inputs[k%16];
                if(op==15 && k>=16)a[i]^=(word)1<<(SEW-1);
#if SCALAR_FORMS
                b[i]=inputs[scalar_indices[seed]];
#else
                b[i]=inputs[(k*3+k/16*5)%16];
#endif
                output[i+1]=inputs[(k*7+11)%16];}
            output[0]=output[cap+1]=(word)0x5b;
            unsigned long status=functions[op](a,b,output+1,vl,cap,mask,rm,flags);
            if((uint32_t)status)++errors;
            for(unsigned i=0;i<cap;++i){unsigned k=(i+seed*11)%32,active=i<vl && ((mask[i/8]>>(i%8))&1);
#if SCALAR_FORMS
                struct fixture result=expected[seed][rm][op][k];
#else
                struct fixture result=expected[rm][op][k];
#endif
                word wanted=active ? result.bits:inputs[(k*7+11)%16];
                if(active)flags|=result.flags;
                if(output[i+1]!=wanted)++errors;}
            flags_seen|=flags;
            if((status>>32)!=flags)++errors;
            if(output[0]!=(word)0x5b || output[cap+1]!=(word)0x5b)++errors;
            ++cases;
        }
        if(errors!=prior){text("RVV_FP_DETAIL op=");num(op);text(" seed=");num(seed);text(" errors=");num(errors-prior);text("\n");}
    }
    text(errors ? "RVV_FP_FAIL sew=":"RVV_FP_PASS sew=");num(SEW);text(" cases=");num(cases);
    text(" errors=");num(errors);text(" flags_seen=");num(flags_seen);text("\n");
    syscall3(94,errors ? 1:0,0,0);for(;;){}
}
__asm__(".global _start\n_start:\n.option push\n.option norelax\nla gp,__global_pointer$\n.option pop\ntail probe_main\n");
