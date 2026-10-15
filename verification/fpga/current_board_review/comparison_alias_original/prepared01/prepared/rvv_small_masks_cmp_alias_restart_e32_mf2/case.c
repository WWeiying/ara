#include <stdint.h>
#include "operations.h"
#ifndef RESTART_MASKS
#define RESTART_MASKS 0
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
static word a[1024],b[1024];
static uint64_t output[1026];
static uint8_t predicate[128];
extern unsigned long capacity(void);
typedef unsigned long (*operation)(const void *,const void *,void *,unsigned long,unsigned long,const void *,unsigned long);
static operation functions[]={FUNCTIONS};
extern long replay_write(long,long,long,long);
#define syscall3 replay_write
static void text(const char *s){long n=0;while(s[n])++n;syscall3(64,1,(long)s,n);}
static void num(uint64_t n){char s[24];unsigned i=23;s[i]=0;do{s[--i]='0'+n%10;n/=10;}while(n);text(s+i);}
static unsigned bit(const void *p,unsigned i){return (((const uint8_t *)p)[i/8]>>(i%8))&1;}
static int64_t sign(word x){uint64_t s=UINT64_C(1)<<(SEW-1);return ((uint64_t)x^s)-s;}
int rvv_small_masks_cmp_alias_restart_e32_mf2_main(void) {
    unsigned cap=capacity(),errors=0,cases=0,printed=0;
    if(!cap || cap>1024){text("RVV_MASK_CAPACITY_FAIL\n");return 2;}
    unsigned lengths[]={8};
    unsigned long max_start=0;
    if(RESTART_MASKS){
        __asm__ volatile("csrr %0,vlenb":"=r"(max_start));
        max_start=max_start*8-1;
    }
#if CARRY_FORMS
    static const unsigned mapping[]={CARRY_ORACLE},scalar[]={CARRY_SCALAR},
        immediate[]={CARRY_IMMEDIATE},carry_input[]={CARRY_INPUT};
    static const int constants[]={CARRY_VALUES};
#endif
    for(unsigned seed=0;seed<1;++seed) {
        uint64_t rng=UINT64_C(0xc274caf34727a125)^seed;
        for(unsigned i=0;i<cap;++i){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;a[i]=rng;b[i]=rng>>19;if(i%8==0)b[i]=a[i];}
#if CARRY_FORMS
        for(unsigned i=0;i<cap;++i){
            if(i%8==0){a[i]=(word)-1;b[i]=1;}
            if(i%8==1){a[i]=0;b[i]=(word)-1;}
            if(i%8==2){a[i]=(word)(UINT64_C(1)<<(SEW-1));b[i]=a[i];}
            if(i%8==3){a[i]=(word)-1;b[i]=(word)-1;}
        }
        b[0]=seed==0 ? 0:seed==1 ? (word)-1:(word)(UINT64_C(1)<<(SEW-1));
#endif
#if SCALAR_FORMS
        const word boundaries[]={(word)-3,(word)-4,(word)-2,0,(word)-1,
                                 (word)(UINT64_C(1)<<(SEW-1)),
                                 (word)((UINT64_C(1)<<(SEW-1))-1)};
        for(unsigned i=0;i<cap;++i)
            if(i%2==0)a[i]=boundaries[(i/2+seed)%7];
#endif
        for(unsigned raw_op=0;raw_op<1;++raw_op) {
#if CARRY_FORMS
        unsigned op=mapping[raw_op];
#elif COMPARISON_ALIASES
        unsigned op=raw_op%6;
#elif ALIASES
        unsigned op=8+raw_op%8;
#elif SCALAR_FORMS
        unsigned op=raw_op%6;
#else
        unsigned op=raw_op;
#endif
        unsigned prior=errors;
        for(unsigned l=0;l<1;++l)for(unsigned mode=0;mode<1;++mode)
        for(unsigned trial=0;trial<1U;++trial) {
            unsigned vl=lengths[l],count=0,start=0;int64_t first=-1;
            if(RESTART_MASKS)
                start=trial==0 ? 1:trial==1 ? vl/2:trial==2 ? (vl<=max_start ? vl:cap-1):cap-1;
            start=4;
            for(unsigned i=0;i<128;++i)predicate[i]=mode==0 ? 255:mode==1 ? 0:mode==2 ? 0xaa:0x24;
            for(unsigned i=0;i<1026;++i)output[i]=UINT64_C(0x5b5b5b5b5b5b5b5b);
            if(RESTART_MASKS && !seed && !raw_op && !mode){
                text("RVV_MASK_TRIAL vl=");num(vl);text(" vstart=");num(start);text("\n");
                (void)0; /* Linux UART drain only. */
            }
            unsigned long returned=functions[raw_op](a,b,output+1,vl,cap,predicate,start);
            if(returned)++errors;
            for(unsigned i=0;i<cap;++i) {
                unsigned before_element=errors;
                unsigned active=i>=start && i<vl,selected=bit(predicate,i),x=bit(a,i),y=bit(b,i),expected=0;
                if(op<6 || op>=20)active&=selected;
                word rhs=SCALAR_FORMS ? (word)-3:b[i];
#if CARRY_FORMS
                rhs=immediate[raw_op] ? (word)constants[raw_op]:scalar[raw_op] ? b[0]:b[i];
                unsigned carry=carry_input[raw_op] && selected;
#endif
                if(op==0)expected=a[i]==rhs;
                if(op==1)expected=a[i]!=rhs;
                if(op==2)expected=a[i]<rhs;
                if(op==3)expected=sign(a[i])<sign(rhs);
                if(op==4)expected=a[i]<=rhs;
                if(op==5)expected=sign(a[i])<=sign(rhs);
#if CARRY_FORMS
                if(op==6)expected=((unsigned __int128)a[i]+rhs+carry)>>SEW;
                if(op==7)expected=(unsigned __int128)a[i]<(unsigned __int128)rhs+carry;
#else
                if(op==6)expected=((uint64_t)a[i]+b[i]<(uint64_t)a[i]) || (word)(a[i]+b[i])<a[i] || (selected && (word)(a[i]+b[i])==(word)-1);
                if(op==7)expected=a[i]<b[i] || (selected && a[i]==b[i]);
#endif
                if(op==8)expected=x&y;
                if(op==9)expected=!(x&y);
                if(op==10)expected=x&!y;
                if(op==11)expected=x^y;
                if(op==12)expected=x|y;
                if(op==13)expected=!(x|y);
                if(op==14)expected=x|!y;
                if(op==15)expected=!(x^y);
                if(op==20)expected=count==0 && !x;
                if(op==21)expected=count==0;
                if(op==22)expected=count==0 && x;
                if(op<16 || op>=20) {
                    unsigned actual=bit(output+1,i),old=(0x5b>>(i%8))&1;
#if ALIASES
                    old=raw_op<8 ? x:y;
#endif
#if COMPARISON_ALIASES
                    old=raw_op<6 ? x:y;
#endif
                    if(active){if(actual!=expected)++errors;}
                    else if(start>=vl || i<start){if(actual!=old)++errors;}
                    else if(i<vl){
                        /* A different-EEW source overlap forces mask agnostic. */
                        if(actual!=old && !(COMPARISON_ALIASES && actual==1))++errors;
                    } else if(actual!=old && actual!=1 && actual!=expected)++errors;
                    if(errors!=before_element && !printed++) {
                        text("RVV_MASK_BIT seed=");num(seed);text(" op=");num(raw_op);
                        text(" vl=");num(vl);text(" mask=");num(mode);text(" vstart=");num(start);
                        text(" element=");num(i);text(" active=");num(active);
                        text(" old=");num(old);text(" expected=");num(active ? expected:old);
                        text(" actual=");num(actual);text("\n");
                    }
                } else if(op==18 || op==19) {
                    word wanted=i<vl && selected ? (op==18 ? count:i):(word)UINT64_C(0x5b5b5b5b5b5b5b5b);
                    if(((word *)(output+1))[i]!=wanted)++errors;
                }
                if((i<vl || op>=20) && x && selected){if(first<0)first=i;++count;}
            }
            if(op==16 && output[1]!=count)++errors;
            if(op==17 && output[1]!=(uint64_t)first)++errors;
            if(output[0]!=UINT64_C(0x5b5b5b5b5b5b5b5b) || output[1025]!=UINT64_C(0x5b5b5b5b5b5b5b5b))++errors;
            ++cases;
            if(errors) {
                text("RVV_MASK_FIRST seed=");num(seed);text(" op=");num(raw_op);
                text(" vl=");num(vl);text(" mask=");num(mode);text(" vstart=");num(start);
                text(" returned_vstart=");num(returned);text(" errors=");num(errors);
                text(" guard_before=");num(output[0]);text(" guard_after=");num(output[1025]);
                text("\n");goto probe_done;
            }
        }
        if(errors!=prior){text("RVV_MASK_DETAIL op=");num(raw_op);text(" seed=");num(seed);text(" errors=");num(errors-prior);text("\n");}
        }
    }
probe_done:
    text(errors ? "RVV_MASK_FAIL sew=":"RVV_MASK_PASS sew=");num(SEW);text(" cases=");num(cases);text(" errors=");num(errors);text("\n");
    return errors ? 1:0;
}
