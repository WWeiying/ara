/* Architectural port of tail_vl15; original identity in provenance.json.
 * Not an original Linux ELF replay or a fault/restart OS test. */
#include <stdint.h>
#include "operations.h"
#ifndef UNMASKED_COMPARISONS
#define UNMASKED_COMPARISONS 0
#endif
#ifndef DESTINATION_KIND
#define DESTINATION_KIND 0
#endif
#ifndef RESTART_COMPARISONS
#define RESTART_COMPARISONS 0
#endif
#ifndef UNBOXED_COMPARISONS
#define UNBOXED_COMPARISONS 0
#endif
#if SEW == 16
typedef uint16_t word;
#elif SEW == 32
typedef uint32_t word;
#else
typedef uint64_t word;
#endif
struct fixture {unsigned bit,flags;};
#include "fixtures.h"
static word a[1024],b[1024];
static uint8_t mask[128],output[130];
extern unsigned long capacity(void);
typedef unsigned long (*operation)(const void *,const void *,void *,unsigned long,
                                   unsigned long,const void *,unsigned long,unsigned long);
static operation functions[]={FUNCTIONS};
extern long replay_write(long, long, long, long);
#define syscall3 replay_write
static void text(const char *s) {long n=0;while(s[n])++n;syscall3(64,1,(long)s,n);}
static void num(uint64_t n) {char s[24];unsigned i=23;s[i]=0;do{s[--i]='0'+n%10;n/=10;}while(n);text(s+i);}
static unsigned bit(const uint8_t *p,unsigned i) {return (p[i/8]>>(i%8))&1;}
static unsigned lhs_index(unsigned seed,unsigned i) {return (i+seed+7*(seed/16))%16;}
static unsigned rhs_index(unsigned seed,unsigned i,unsigned op) {
    return op<4 ? (i*3+seed*5+seed/16)%16:seed%16;
}
#include "audit.h"
int tail_vl15_main(void) {
    unsigned cap=capacity(),errors=0,cases=0,details=0;
    if(cap != 16){text("RVV_FP_COMPARE_CAPACITY_FAIL\n");return 2;}
    unsigned bytes=(cap+7)/8;
    {
        unsigned seed=0;
        unsigned op=4;
        unsigned vl=15;
        unsigned mode=0;
        unsigned sticky=0;
        unsigned start=0;
        unsigned prior=errors,flags=sticky;
        text("RVV_REDUCED_BEGIN cases=1\n");
        for(unsigned i=0;i<128;++i)
            mask[i]=mode==0 ? 255:mode==1 ? 0xaa:mode==2 ? 0x24:0;
        for(unsigned i=0;i<cap;++i) {
            a[i]=inputs[mapped(lhs_index(seed,i))];
            b[i]=inputs[mapped(rhs_index(seed,i,op))];
        }
        for(unsigned i=0;i<130;++i)output[i]=0x5b;
        if(CONTROL == 1)mask[0]=32;
        audit_before(cap,op,vl,start);
        if(RESTART_COMPARISONS && !seed && !op && !mode && !sticky) {
            text("RVV_FP_COMPARE_TRIAL vl=");num(vl);text(" vstart=");num(start);text("\n");
            /* Linux TIOCOUTQ omitted; timing is not equivalent. */
        }
        unsigned long status=functions[op](a,b,output+1,vl,cap,mask,start,sticky);
        capture_vectors(seen_a,seen_b,seen_mask);
        if((uint32_t)status)++errors;
        for(unsigned i=0;i<cap;++i) {
            unsigned ai=lhs_index(seed,i),bi=rhs_index(seed,i,op);
            /* Quiet-NaN payloads have identical comparison/exception semantics. */
            if(UNBOXED_COMPARISONS && op>=4)bi=14;
            ai=mapped(ai);bi=mapped(bi);
            struct fixture wanted=expected[op<4 ? op:op-4][ai][bi];
            unsigned old=(0x5b>>(i%8))&1,actual=bit(output+1,i);
#if DESTINATION_KIND == 1
            old=((uint64_t)a[i/SEW]>>(i%SEW))&1;
#elif DESTINATION_KIND == 2
            old=((uint64_t)b[i/SEW]>>(i%SEW))&1;
#elif DESTINATION_KIND == 3
            old=bit(mask,i);
#endif
            unsigned active=i>=start && i<vl && (UNMASKED_COMPARISONS || bit(mask,i));
            if(active) {
                flags|=wanted.flags;
                if(actual!=wanted.bit)++errors;
            } else if(start>=vl || i<start) {
                if(actual!=old)++errors;
            } else if(i<vl) {
                /* A different-EEW source overlap forces mask agnostic. */
                unsigned agnostic=DESTINATION_KIND==1 || (DESTINATION_KIND==2 && op<4);
                if(actual!=old && !(agnostic && actual==1))++errors;
            } else if(actual!=old && actual!=1 && actual!=wanted.bit)++errors;
        }
        if((status>>32)!=flags)++errors;
        if(output[0]!=0x5b || output[bytes+1]!=0x5b)++errors;
        if(errors!=prior && details++<20) {
            text("RVV_FP_COMPARE_DETAIL op=");num(op);text(" seed=");num(seed);
            text(" vl=");num(vl);text(" mask=");num(mode);text(" sticky=");num(sticky);
            if(RESTART_COMPARISONS){text(" vstart=");num(start);}
            text(" expected_flags=");num(flags);text(" actual_flags=");num(status>>32);
            text(" errors=");num(errors-prior);text("\n");
        }
        unsigned extra=audit_after(cap,op,vl,start,status,errors-prior);
        errors+=extra;
        ++cases;
    }
    text(errors ? "RVV_FP_COMPARE_FAIL sew=":"RVV_FP_COMPARE_PASS sew=");num(SEW);
    text(" cases=");num(cases);text(" errors=");num(errors);text("\n");
    return errors ? 1 : 0;
}
