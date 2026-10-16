#include <stdint.h>
static uint8_t input[8192] __attribute__((aligned(64)));
static uint8_t output[8192] __attribute__((aligned(64)));
static uint8_t mask[128];
extern unsigned long capacity(void);
extern unsigned long op_0(const void *,void *,const void *,unsigned long,unsigned long,long,unsigned long);
static long call(long n,long x,long y,long z) {
    register long a0 __asm__("a0")=x,a1 __asm__("a1")=y,a2 __asm__("a2")=z,a7 __asm__("a7")=n;
    __asm__ volatile("ecall":"+r"(a0):"r"(a1),"r"(a2),"r"(a7):"memory");return a0;
}
static void text(const char *s) {long n=0;while(s[n])++n;call(64,1,(long)s,n);}
static void quit(unsigned n) {call(94,n,0,0);for(;;){}}
void probe_main(void) {
    unsigned cap=capacity();
    if(!cap || cap>1024){text("RVV_SETUP_CAPACITY_FAIL\n");quit(2);}
    for(unsigned i=0;i<8192;++i){input[i]=(i*73+(i>>4)*37)^0x85;output[i]=0x5b;}
    for(unsigned i=0;i<128;++i)mask[i]=255;
    text("RVV_SETUP_BEGIN seed=0 op=0 reverse=0 offset=1 vl=0 mask=0 vstart=0\n");
    unsigned errors=op_0(input+65,output+65,mask,0,cap,3*(SEW/8),0)!=0;
    for(unsigned i=0;i<8192;++i)if(output[i]!=0x5b)++errors;
    text(errors ? "RVV_SETUP_FAIL cases=1\n":"RVV_SETUP_PASS cases=1\n");
    quit(errors ? 1:0);
}
__asm__(".global _start\n_start:\n.option push\n.option norelax\n"
        "la gp,__global_pointer$\n.option pop\ntail probe_main\n");
