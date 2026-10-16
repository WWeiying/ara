#include <stdint.h>
#include "operations.h"
#ifndef RESTART_MEMORY
#define RESTART_MEMORY 0
#endif
#if SEW == 8
typedef uint8_t word;
#elif SEW == 16
typedef uint16_t word;
#elif SEW == 32
typedef uint32_t word;
#else
typedef uint64_t word;
#endif
static word input[8192],index_data[1024],output[8192],expected[8192],second[1024];
static uint8_t mask[128];
extern unsigned long capacity(void);
typedef unsigned long (*operation)(const void *,const void *,void *,unsigned long,unsigned long,const void *,long,void *,unsigned long);
static operation functions[]={FUNCTIONS};
static long syscall3(long n,long x,long y,long z) {
    register long a0 __asm__("a0")=x,a1 __asm__("a1")=y,a2 __asm__("a2")=z,a7 __asm__("a7")=n;
    __asm__ volatile("ecall":"+r"(a0):"r"(a1),"r"(a2),"r"(a7):"memory");return a0;
}
static void text(const char *s){long n=0;while(s[n])++n;syscall3(64,1,(long)s,n);}
static void num(uint64_t n){char s[24];unsigned i=23;s[i]=0;do{s[--i]='0'+n%10;n/=10;}while(n);text(s+i);}
static unsigned selected(unsigned mode,unsigned i){return mode==0 || (mode==1 ? i&1 : mode==2 ? i%7==2:0);}
void probe_main(void) {
    unsigned cap=capacity(),errors=0,cases=0,skips=0,details=0;
    if(!cap || cap>1024){text("RVV_MEMORY_CAPACITY_FAIL\n");syscall3(94,2,0,0);for(;;){}}
    unsigned lengths[]={0,1,2,3,cap/2,cap-1,cap};
    unsigned long max_start=0;
    if(RESTART_MEMORY){
        __asm__ volatile("csrr %0,vlenb":"=r"(max_start));
        max_start=max_start*8-1;
    }
    for(unsigned seed=0;seed<3;++seed)for(unsigned op=0;op<10;++op)
    for(unsigned l=0;l<7;++l)for(unsigned mode=0;mode<4;++mode)
    for(unsigned st=0;st<((op==2 || op==3) ? 3u:1u);++st)
    for(unsigned trial=0;trial<(RESTART_MEMORY ? 4U:1U);++trial) {
        unsigned vl=lengths[l],start=0,prior=errors;long stride=st==0 ? 2:st==1 ? -2:0;
        if(RESTART_MEMORY)
            start=trial==0 ? 1:trial==1 ? vl/2:trial==2 ? (vl<=max_start ? vl:cap-1):cap-1;
        unsigned base=(op==2 || op==3) && stride<0 ? 4096:16;
        if(op>=8 && !SEGMENT_ALLOWED){++skips;continue;}
        if(op==3 && st==2){++skips;continue;}
        if(op>=4 && op<=7 && vl>128/sizeof(word)){++skips;continue;}
        for(unsigned i=0;i<8192;++i){input[i]=(word)(i*37+seed*71+1);output[i]=expected[i]=(word)0x5b;}
        for(unsigned i=0;i<1024;++i){index_data[i]=(word)(((i*7)%(128/sizeof(word)))*sizeof(word));second[i]=(word)0x5b;}
        for(unsigned i=0;i<128;++i)mask[i]=0;
        for(unsigned i=0;i<cap;++i)if(selected(mode,i))mask[i/8]|=1u<<(i%8);
        if(op==9)for(unsigned i=0;i<cap;++i)second[i]=(word)(i*19+seed*11);
        for(unsigned i=start;i<vl;++i)if(selected(mode,i)) {
            if(op==0)expected[base+i]=input[base+i];
            if(op==1)expected[base+i]=input[base+i];
            if(op==2)expected[base+i]=input[base+(long)i*stride];
            if(op==3)expected[base+(long)i*stride]=input[base+i];
            if(op==4 || op==5)expected[base+i]=input[base+index_data[i]/sizeof(word)];
            if(op==6 || op==7)expected[base+index_data[i]/sizeof(word)]=input[base+i];
            if(op==8)expected[base+i]=input[base+2*i];
            if(op==9){expected[base+2*i]=input[base+i];expected[base+2*i+1]=second[i];}
        }
        if(RESTART_MEMORY && !seed && !op && !mode && !st){
            text("RVV_MEMORY_TRIAL vl=");num(vl);text(" vstart=");num(start);text("\n");
            syscall3(29,1,0x5409,1);
        }
        if(functions[op](input+base,index_data,output+base,vl,cap,mask,stride*sizeof(word),second,start))++errors;
        for(unsigned i=0;i<8192;++i)if(output[i]!=expected[i])++errors;
        if(op==8)for(unsigned i=0;i<cap;++i)if(second[i]!=(i>=start && i<vl && selected(mode,i) ? input[base+2*i+1]:(word)0x5b))++errors;
        if(RESTART_MEMORY && errors!=prior && details++<20){
            text("RVV_MEMORY_DETAIL op=");num(op);text(" seed=");num(seed);
            text(" vl=");num(vl);text(" vstart=");num(start);text(" mask=");num(mode);
            text(" stride_case=");num(st);text(" errors=");num(errors-prior);text("\n");
        }
        ++cases;
    }
    text(errors ? "RVV_MEMORY_FAIL sew=":"RVV_MEMORY_PASS sew=");num(SEW);
    text(" cases=");num(cases);text(" skips=");num(skips);text(" errors=");num(errors);text("\n");
    syscall3(94,errors ? 1:0,0,0);for(;;){}
}
__asm__(".global _start\n_start:\n.option push\n.option norelax\nla gp,__global_pointer$\n.option pop\ntail probe_main\n");
