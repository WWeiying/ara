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
#if SEW == 16
typedef uint16_t word;
#elif SEW == 32
typedef uint32_t word;
#else
typedef uint64_t word;
#endif
struct fixture {unsigned bit,flags;};
#include "tables.h"
typedef uint64_t alias64 __attribute__((__may_alias__));
static word a[1024] __attribute__((aligned(8))),b[1024] __attribute__((aligned(8)));
static uint8_t mask[128],output[130];
extern unsigned long capacity(void);
typedef unsigned long (*operation)(const void *,const void *,void *,unsigned long,
                                   unsigned long,const void *,unsigned long,unsigned long);
static operation functions[]={FUNCTIONS};
extern long replay_write(long,long,long,long);
#define syscall3 replay_write
static void text(const char *s) {long n=0;while(s[n])++n;syscall3(64,1,(long)s,n);}
static void num(uint64_t n) {char s[24];unsigned i=23;s[i]=0;do{s[--i]='0'+n%10;n/=10;}while(n);text(s+i);}
int alias_v8_e16m8_prefix700_main(void) {
    unsigned cap=capacity(),errors=0,cases=0,details=0;
    if(cap!=512){text("RVV_FP_COMPARE_CAPACITY_FAIL\n");return 2;}
    unsigned lengths[]={0,1,2,3,cap/2,cap-1,cap},bytes=(cap+7)/8;
    for(unsigned seed=0;seed<32;++seed)for(unsigned op=0;op<10;++op)
    for(unsigned l=0;l<7;++l)for(unsigned mode=0;mode<4;++mode)
    for(unsigned sticky=0;sticky<2;++sticky)
    for(unsigned trial=0;trial<(RESTART_COMPARISONS ? 4U:1U);++trial) {
        unsigned prior=errors,vl=lengths[l],flags=sticky,start=0;
        if(RESTART_COMPARISONS)
            start=trial==0 ? 1:trial==1 ? vl/2:trial==2 ? vl:cap-1;
        for(unsigned i=0;i<128;++i)
            mask[i]=mode==0 ? 255:mode==1 ? 0xaa:mode==2 ? 0x24:0;
        const struct packed_case *pc=&packed_cases[cases];
        if(pc->seed!=seed || pc->op!=op || pc->vl!=vl || pc->mode!=mode || pc->sticky!=sticky) return 3;
        for(unsigned i=0;i<128;++i) {
            ((alias64 *)a)[i]=input_rows[pc->ai][i];
            ((alias64 *)b)[i]=input_rows[pc->bi][i];
        }
        for(unsigned i=0;i<130;++i)output[i]=0x5b;
        if(RESTART_COMPARISONS && !seed && !op && !mode && !sticky) {
            text("RVV_FP_COMPARE_TRIAL vl=");num(vl);text(" vstart=");num(start);text("\n");
            (void)0; /* Linux UART drain only. */
        }
        unsigned long status=functions[op](a,b,output+1,vl,cap,mask,start,sticky);
        if((uint32_t)status)++errors;
        for(unsigned i=0;i<64;++i) {
            unsigned actual=output[i+1];
            if((actual&pc->zero[i]) | ((~actual)&pc->one[i])) ++errors;
        }
        flags=pc->flags;
        if((status>>32)!=flags)++errors;
        if(output[0]!=0x5b || output[bytes+1]!=0x5b)++errors;
        if(errors!=prior && details++<20) {
            text("RVV_FP_COMPARE_DETAIL op=");num(op);text(" seed=");num(seed);
            text(" vl=");num(vl);text(" mask=");num(mode);text(" sticky=");num(sticky);
            if(RESTART_COMPARISONS){text(" vstart=");num(start);}
            text(" expected_flags=");num(flags);text(" actual_flags=");num(status>>32);
            text(" errors=");num(errors-prior);text("\n");
        }
        ++cases;
        if(cases==700)goto prefix_done;
    }
prefix_done:
    text(errors ? "RVV_FP_COMPARE_FAIL sew=":"RVV_FP_COMPARE_PASS sew=");num(SEW);
    text(" cases=");num(cases);text(" errors=");num(errors);text("\n");
    return errors ? 1:0;
}
