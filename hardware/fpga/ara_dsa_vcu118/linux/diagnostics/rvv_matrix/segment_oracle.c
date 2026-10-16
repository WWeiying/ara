#include <stdint.h>
#include "operations.h"
#ifndef RESTART_SEGMENTS
#define RESTART_SEGMENTS 0
#endif
static uint8_t input[8192] __attribute__((aligned(64)));
static uint8_t output[8192] __attribute__((aligned(64)));
static uint8_t expected[8192],mask[128];
#if INDEXED
#ifndef INDEX_SEW
#define INDEX_SEW 32
#endif
#if INDEX_SEW == 8
typedef uint8_t index_word;
#elif INDEX_SEW == 16
typedef uint16_t index_word;
#elif INDEX_SEW == 32
typedef uint32_t index_word;
#else
typedef uint64_t index_word;
#endif
static index_word indexes[1024];
#endif
static const unsigned fields[]={FIELDS};
extern unsigned long capacity(void);
typedef unsigned long (*operation)(const void *,void *,const void *,unsigned long,unsigned long,long,unsigned long);
static operation functions[]={FUNCTIONS};
static long syscall3(long n,long x,long y,long z){
    register long a0 __asm__("a0")=x,a1 __asm__("a1")=y,a2 __asm__("a2")=z,a7 __asm__("a7")=n;
    __asm__ volatile("ecall":"+r"(a0):"r"(a1),"r"(a2),"r"(a7):"memory");return a0;
}
static void text(const char *s){long n=0;while(s[n])++n;syscall3(64,1,(long)s,n);}
static void num(uint64_t n){char s[24];unsigned i=23;s[i]=0;do{s[--i]='0'+n%10;n/=10;}while(n);text(s+i);}
void probe_main(void){
    unsigned fullcap=capacity(),errors=0,cases=0;
    if(!fullcap || fullcap>1024){text("RVV_SEGMENT_CAPACITY_FAIL\n");syscall3(94,2,0,0);for(;;){}}
    unsigned long max_start=0;
    if(RESTART_SEGMENTS){
        __asm__ volatile("csrr %0,vlenb":"=r"(max_start));
        max_start=max_start*8-1;
    }
    for(unsigned seed=0;seed<3;++seed){
        for(unsigned i=0;i<8192;++i)input[i]=(i*73+seed*19+(i>>4)*37)^0x85;
        for(unsigned op=0;op<OP_COUNT;++op)for(unsigned reverse=0;reverse<(!INDEXED && op%4>=2 ? 2u:1u);++reverse)
        for(unsigned offset=MISALIGNED ? 1:0;offset<(MISALIGNED ? SEW/8:1);++offset)
        for(unsigned l=0;l<7;++l)for(unsigned mode=0;mode<4;++mode)
        for(unsigned trial=0;trial<(RESTART_SEGMENTS ? 4U:1U);++trial){
            unsigned nf=fields[op],bytes=SEW/8,cap=fullcap,store=op%2,start=0;
#if INDEXED && INDEX_SEW == 8
            unsigned limit=256/((nf+2)*bytes),bounded=1;
            while(bounded<=limit/2)bounded*=2;
            if(cap>bounded)cap=bounded;
#endif
            unsigned lengths[]={0,1,2,3,cap/2,cap-1,cap};
            unsigned vl=lengths[l];
            if(vl>cap)vl=cap;
            if(RESTART_SEGMENTS)
                start=trial==0 ? 1:trial==1 ? vl/2:trial==2 ? (vl<=max_start ? vl:cap-1):cap-1;
            long stride=(op%4>=2 ? nf+2:nf)*bytes;
            unsigned data_base=64+offset,base=data_base+(reverse ? (cap-1)*stride:0);
            if(reverse)stride=-stride;
#if INDEXED
            base=data_base;
            for(unsigned i=0;i<cap;++i)indexes[i]=((i*5+3)%cap)*(nf+2)*bytes;
#endif
            if(base+nf*bytes>=8192 || data_base+(cap-1)*(nf+2)*bytes+nf*bytes>=8192){
                text("RVV_SEGMENT_BOUNDS_FAIL\n");syscall3(94,2,0,0);for(;;){}}
            for(unsigned i=0;i<128;++i)mask[i]=mode==0 ? 255:mode==1 ? 0:mode==2 ? 0xaa:0x24;
            for(unsigned i=0;i<8192;++i)output[i]=expected[i]=0x5b;
            for(unsigned i=start;i<vl;++i)if((mask[i/8]>>(i%8))&1)
                for(unsigned field=0;field<nf;++field)for(unsigned b=0;b<bytes;++b){
                    unsigned packed=data_base+(field*cap+i)*bytes+b;
                    unsigned memory=base+
#if INDEXED
                        indexes[i]+
#else
                        i*stride+
#endif
                        field*bytes+b;
                    if(store)expected[memory]=input[packed];else expected[packed]=input[memory];
                }
            long addressing=stride;
#if INDEXED
            addressing=(long)indexes;
#endif
            if(RESTART_SEGMENTS && !seed && !op && !reverse && !mode){
                text("RVV_SEGMENT_TRIAL vl=");num(vl);text(" vstart=");num(start);text("\n");
                syscall3(29,1,0x5409,1);
            }
            if(functions[op](input+(store ? data_base:base),output+(store ? base:data_base),mask,vl,cap,addressing,start))++errors;
            for(unsigned i=0;i<8192;++i)if(output[i]!=expected[i]){
                if(errors<20){text("RVV_SEGMENT_DETAIL op=");num(op);text(" vl=");num(vl);
                    text(" mask=");num(mode);text(" offset=");num(offset);text(" byte=");num(i);text(" expected=");num(expected[i]);
                    if(RESTART_SEGMENTS){text(" vstart=");num(start);}
                    text(" actual=");num(output[i]);text("\n");}
                ++errors;
            }
            ++cases;
        }
    }
    text(errors ? "RVV_SEGMENT_FAIL sew=":"RVV_SEGMENT_PASS sew=");num(SEW);
    text(" cases=");num(cases);text(" errors=");num(errors);text("\n");
    syscall3(94,errors ? 1:0,0,0);for(;;){}
}
__asm__(".global _start\n_start:\n.option push\n.option norelax\nla gp,__global_pointer$\n.option pop\ntail probe_main\n");
