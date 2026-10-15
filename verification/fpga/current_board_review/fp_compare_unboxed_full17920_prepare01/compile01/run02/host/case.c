/* Full original source-derived port. Compile admission is separate. */
#if SEW != 16 || UNMASKED_COMPARISONS != 1 || UNBOXED_COMPARISONS != 1 || RESTART_COMPARISONS != 0 || DESTINATION_KIND != 0
#error Wrong original source configuration
#endif
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
static word a[1024] __attribute__((aligned(8)));
static word b[1024] __attribute__((aligned(8)));
static uint8_t mask[128] __attribute__((aligned(8)));
static uint8_t output[130] __attribute__((aligned(8)));
#include "packed_core.h"
#include "generated_tables.h"
extern unsigned long capacity(void);
typedef unsigned long (*operation)(const void *,const void *,void *,unsigned long,
                                   unsigned long,const void *,unsigned long,unsigned long);
static operation functions[]={FUNCTIONS};
extern long replay_write(long,long,long,long);
#define syscall3 replay_write
static void text(const char *s) {long n=0;while(s[n])++n;syscall3(64,1,(long)s,n);}
static void num(uint64_t n) {char s[24];unsigned i=23;s[i]=0;do{s[--i]='0'+n%10;n/=10;}while(n);text(s+i);}
int fp_compare_unboxed_e16_mf4_full17920_main(void) {
    unsigned cap=capacity(),errors=0,cases=0,details=0;
    if(cap!=16){text("RVV_FP_COMPARE_CAPACITY_FAIL\n");return 2;}
    unsigned lengths[]={0,1,2,3,cap/2,cap-1,cap};
    for(unsigned seed=0;seed<32;++seed)for(unsigned op=0;op<10;++op)
    for(unsigned l=0;l<7;++l)for(unsigned mode=0;mode<4;++mode)
    for(unsigned sticky=0;sticky<2;++sticky)
    for(unsigned trial=0;trial<(RESTART_COMPARISONS ? 4U:1U);++trial) {
        unsigned prior=errors,vl=lengths[l],flags=sticky,start=0;
        if(RESTART_COMPARISONS)
            start=trial==0 ? 1:trial==1 ? vl/2:trial==2 ? vl:cap-1;
        uint64_t record=oracle_records[(seed*10+op)*7+l];
        uint64_t maskword=(uint64_t)(mode==0 ? 255:mode==1 ? 0xaa:mode==2 ? 0x24:0)*UINT64_C(0x0101010101010101);
        ALL_16_SD(mask,maskword);
        fresh_inputs(a,b,input_periods[(record>>48)&255],input_periods[record>>56]);
        ALL_16_SD(output,UINT64_C(0x5b5b5b5b5b5b5b5b));
        SH_AT(output,128,0x5b5b);
        if(RESTART_COMPARISONS && !seed && !op && !mode && !sticky) {
            text("RVV_FP_COMPARE_TRIAL vl=");num(vl);text(" vstart=");num(start);text("\n");
            syscall3(29,1,0x5409,1);
        }
        unsigned long status=functions[op](a,b,output+1,vl,cap,mask,start,sticky);
        flags|=(unsigned)((record>>32)&255);
        errors+=packed_errors(result_and_guards(output),status,record,flags);
        if(errors!=prior && details++<20) {
            text("RVV_FP_COMPARE_DETAIL op=");num(op);text(" seed=");num(seed);
            text(" vl=");num(vl);text(" mask=");num(mode);text(" sticky=");num(sticky);
            if(RESTART_COMPARISONS){text(" vstart=");num(start);}
            text(" expected_flags=");num(flags);text(" actual_flags=");num(status>>32);
            text(" errors=");num(errors-prior);text("\n");
        }
        ++cases;
    }
    text(errors ? "RVV_FP_COMPARE_FAIL sew=":"RVV_FP_COMPARE_PASS sew=");num(SEW);
    text(" cases=");num(cases);text(" errors=");num(errors);text("\n");
    return errors ? 1:0;
}
