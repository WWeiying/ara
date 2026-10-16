#include <stdint.h>
#include "operations.h"
#if SEW == 8
typedef uint8_t word;
#elif SEW == 16
typedef uint16_t word;
#elif SEW == 32
typedef uint32_t word;
#else
typedef uint64_t word;
#endif
#if DEST_SEW == 16
typedef uint16_t result_word;
#elif DEST_SEW == 32
typedef uint32_t result_word;
#else
typedef uint64_t result_word;
#endif
static word input[1024];
static result_word seed_data[128],output[130];
static uint8_t mask[128];
extern unsigned long capacity(void);
typedef unsigned long (*operation)(const void *,const void *,void *,unsigned long,unsigned long,const void *,unsigned long);
static operation functions[]={FUNCTIONS};
static long syscall3(long n,long x,long y,long z){
    register long a0 __asm__("a0")=x,a1 __asm__("a1")=y,a2 __asm__("a2")=z,a7 __asm__("a7")=n;
    __asm__ volatile("ecall":"+r"(a0):"r"(a1),"r"(a2),"r"(a7):"memory");return a0;
}
static void text(const char *s){long n=0;while(s[n])++n;syscall3(64,1,(long)s,n);}
static void num(uint64_t n){char s[24];unsigned i=23;s[i]=0;do{s[--i]='0'+n%10;n/=10;}while(n);text(s+i);}
#if FLOAT_REDUCTION
static uint64_t from_half(unsigned n,unsigned width){
    unsigned high=0;for(unsigned v=n;v>1;v>>=1)++high;
    unsigned mantissa=width==32 ? 23:52,bias=width==32 ? 127:1023;
    return ((uint64_t)(high+bias-1)<<mantissa)|((uint64_t)(n-(1u<<high))<<(mantissa-high));
}
#endif
void probe_main(void){
    unsigned cap=capacity(),errors=0,cases=0;unsigned long vlenb;
    __asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
    unsigned destcap=vlenb/(DEST_SEW/8);
    if(!cap || cap>1024 || destcap>128){text("RVV_REDUCTION_CAPACITY_FAIL\n");syscall3(94,2,0,0);for(;;){}}
    unsigned lengths[]={0,1,2,3,cap/2,cap-1,cap};
    for(unsigned seed=0;seed<3;++seed){
        for(unsigned i=0;i<cap;++i){
#if FLOAT_REDUCTION
            input[i]=from_half(1u<<((i+seed)%5),SEW);
#else
            input[i]=(word)(UINT64_C(0x9731256dbaf89371)*(i+1+seed));
#endif
        }
        for(unsigned op=0;op<OP_COUNT;++op)for(unsigned rm=0;rm<(FLOAT_REDUCTION ? 5u:1u);++rm)
        for(unsigned l=0;l<7;++l)for(unsigned mode=0;mode<4;++mode){
            unsigned vl=lengths[l];
            for(unsigned i=0;i<128;++i)mask[i]=mode==0 ? 255:mode==1 ? 0:mode==2 ? 0xaa:0x24;
            for(unsigned i=0;i<destcap;++i)seed_data[i]=(result_word)0x5b;
            for(unsigned i=0;i<130;++i)output[i]=(result_word)0x5b;
#if FLOAT_REDUCTION
            unsigned half=2+seed;
            seed_data[0]=from_half(half,DEST_SEW);
            for(unsigned i=0;i<vl;++i)if((mask[i/8]>>(i%8))&1){unsigned x=1u<<((i+seed)%5);
                if(op<2)half+=x;else if(op==2){if(x<half)half=x;}else if(x>half)half=x;}
            result_word wanted=from_half(half,DEST_SEW);
#else
            __int128 sum=seed_data[0];
            for(unsigned i=0;i<vl;++i)if((mask[i/8]>>(i%8))&1){
                uint64_t x=input[i],sign=UINT64_C(1)<<(SEW-1);
                sum+=op==0 ? (__int128)x:(__int128)(int64_t)((x^sign)-sign);}
            result_word wanted=sum;
#endif
            if(functions[op](input,seed_data,output+1,vl,cap,mask,rm))++errors;
            for(unsigned i=0;i<destcap;++i)if(output[i+1]!=(i==0 && vl ? wanted:(result_word)0x5b))++errors;
            if(output[0]!=(result_word)0x5b || output[destcap+1]!=(result_word)0x5b)++errors;
            ++cases;
        }
    }
    text(errors ? "RVV_REDUCTION_FAIL sew=":"RVV_REDUCTION_PASS sew=");num(SEW);text(" cases=");num(cases);
    text(" errors=");num(errors);text("\n");syscall3(94,errors ? 1:0,0,0);for(;;){}
}
__asm__(".global _start\n_start:\n.option push\n.option norelax\nla gp,__global_pointer$\n.option pop\ntail probe_main\n");
