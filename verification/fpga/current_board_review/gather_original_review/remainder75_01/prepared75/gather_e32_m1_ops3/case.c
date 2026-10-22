/* Architectural port of gather_e32_m1_ops3; original identity in provenance.json.
 * Not an original Linux ELF replay or a fault/restart OS test. */
#include <stdint.h>
#ifndef RESTART_PERMUTATIONS
#define RESTART_PERMUTATIONS 0
#endif
#ifndef PERMUTE_OP_MASK
#define PERMUTE_OP_MASK ((1U << OP_COUNT) - 1U)
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
#include "operations.h"
static word input[1024],indices[1024],output[1026];
static uint16_t indices16[1024];
static uint8_t predicate[128];
extern unsigned long capacity(void);
typedef unsigned long (*operation)(const void *,const void *,void *,unsigned long,unsigned long,const void *,unsigned long,unsigned long);
static operation functions[]={FUNCTIONS};
extern long replay_write(long, long, long, long);
#define syscall3 replay_write
static void text(const char *s){long n=0;while(s[n])++n;syscall3(64,1,(long)s,n);}
static void num(uint64_t n){char s[24];unsigned i=23;s[i]=0;do{s[--i]='0'+n%10;n/=10;}while(n);text(s+i);}
static unsigned selected(unsigned mode,unsigned i){return mode==0 || (mode==1 ? i%2:mode==2 && i%7==2);}
static word expected(unsigned op,unsigned i,unsigned vl,unsigned cap,uint64_t scalar,unsigned pick){
    uint64_t index,offset;
    if(op<4 || op==20){
        index=op==0 ? indices[i]:op==1 ? scalar:op==2 ? 0:op==3 ? 31:indices16[i];
        return index<cap ? input[index]:0;
    }
    if(op<8)return !pick ? input[i]:op==4 ? indices[i]:op==5 ? (word)scalar:op==6 ? (word)-16:15;
    if(op<12)return op==8 ? input[i]:op==9 ? (word)scalar:op==10 ? (word)-16:15;
    if(op==18)return i ? input[i-1]:(word)scalar;
    if(op==19)return i+1<vl ? input[i+1]:(word)scalar;
    offset=op<14 ? scalar:op==14 || op==16 ? 0:31;
    if(op==12 || op==14 || op==15)return i>=offset ? input[i-offset]:(word)0x5b;
    /* Guard before addition: XLEN-sized offsets must not wrap into range. */
    return offset<cap && i<cap-offset ? input[i+offset]:0;
}
int gather_e32_m1_ops3_main(void) {
    unsigned cap=capacity(),cases=0,errors=0;
    if(!cap || cap>1024){text("RVV_PERMUTE_CAPACITY_FAIL\n");return 2;}
    const unsigned lengths[]={0,1,2,3,cap/2,cap-1,cap};
    unsigned long max_start=0;
    if(RESTART_PERMUTATIONS){
        __asm__ volatile("csrr %0,vlenb":"=r"(max_start));
        max_start=max_start*8-1;
    }
    const uint64_t scalars[]={0,1,cap-1,cap,cap+1,UINT64_MAX,
                             UINT64_C(1)<<63,(UINT64_C(1)<<63)-1};
    for(unsigned seed=0;seed<1;++seed){
        uint64_t rng=UINT64_C(0xe736815b449aec21)^seed;
        for(unsigned i=0;i<cap;++i){
            rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;input[i]=rng;
            uint64_t index=i%6==0 ? 0:i%6==1 ? 1:i%6==2 ? cap-1:
                           i%6==3 ? cap:i%6==4 ? cap+1:rng%(cap+32);
            indices[i]=index;indices16[i]=index;
        }
        for(unsigned op=3;op<4;++op)for(unsigned s=0;s<1;++s)
        for(unsigned l=2;l<3;++l)for(unsigned mode=0;mode<1;++mode)
        for(unsigned trial=0;trial<1;++trial){
            if(!(PERMUTE_OP_MASK & (1U << op)))continue;
            unsigned vl=lengths[l],start=0;
            if(RESTART_PERMUTATIONS)
                start=trial==0 ? 1:trial==1 ? vl/2:trial==2 ? (vl<=max_start ? vl:cap-1):cap-1;
            if(!(seed==0 && op==3 && s==0 && l==2 && mode==0 && trial==0))continue;
            for(unsigned i=0;i<128;++i)predicate[i]=0;
            for(unsigned i=0;i<cap;++i)if(selected(mode,i))predicate[i/8]|=1u<<(i%8);
            for(unsigned i=0;i<cap+2;++i)output[i]=(word)0x5b;
            const void *index_source=op==20 ? (const void *)indices16:(const void *)indices;
            if(RESTART_PERMUTATIONS && !op && !seed && !s && !mode){
                text("RVV_PERMUTE_TRIAL vl=");num(vl);text(" vstart=");num(start);text("\n");
                /* Linux TIOCOUTQ omitted; timing is not equivalent. */
            }
            if(functions[op](input,index_source,output+1,vl,cap,predicate,scalars[s],start))++errors;
            for(unsigned i=0;i<cap;++i){
                unsigned pick=selected(mode,i);
                word want=i>=start && i<vl && ((op>=4 && op<12) || pick) ?
                          expected(op,i,vl,cap,scalars[s],pick):(word)0x5b;
                if(output[i+1]!=want){
                    if(++errors<=20){text("RVV_PERMUTE_DETAIL op=");num(op);
                        text(" seed=");num(seed);text(" scalar=");num(scalars[s]);
                        text(" vl=");num(vl);text(" mask=");num(mode);text(" element=");num(i);
                        if(RESTART_PERMUTATIONS){text(" vstart=");num(start);}
                        text(" expected=");num(want);text(" actual=");num(output[i+1]);text("\n");}
                }
            }
            if(output[0]!=(word)0x5b || output[cap+1]!=(word)0x5b)++errors;
            ++cases;
        }
    }
    text(errors ? "RVV_PERMUTE_FAIL sew=":"RVV_PERMUTE_PASS sew=");num(SEW);
    text(" cases=");num(cases);text(" errors=");num(errors);text("\n");
    return errors ? 1 : 0;
}
