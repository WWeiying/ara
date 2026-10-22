/* Architectural port of whole_original; original identity in provenance.json.
 * Not an original Linux ELF replay or a fault/restart OS test. */
#include <stdint.h>
#include "operations.h"
static uint8_t input[1024] __attribute__((aligned(64)));
static uint8_t output[1088] __attribute__((aligned(64)));
typedef unsigned long (*operation)(const void *,void *,unsigned long,unsigned long);
static operation functions[]={FUNCTIONS};
extern long replay_write(long, long, long, long);
#define syscall3 replay_write
static void text(const char *s){long n=0;while(s[n])++n;syscall3(64,1,(long)s,n);}
static void num(uint64_t n){char s[24];unsigned i=23;s[i]=0;do{s[--i]='0'+n%10;n/=10;}while(n);text(s+i);}
int whole_original_main(void) {
    unsigned long vlenb;__asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
    unsigned errors=0,cases=0,skips=0;
    if(vlenb<32 || vlenb>128){text("RVV_WHOLE_CAPACITY_FAIL\n");return 2;}
    for(unsigned seed=0;seed<3;++seed)for(unsigned op=WHOLE_OP_BEGIN;op<WHOLE_OP_END;++op)for(unsigned mode=0;mode<5;++mode){
        unsigned n=op<16 ? 1u<<(op/4):1u<<(op-16);
        unsigned bytes=op<16 ? 1u<<(op%4):1u<<mode;
        if(mode==4 && op>=16)bytes=1;
        unsigned evl=n*vlenb/bytes;
        unsigned starts[]={0,1,evl/2,evl,evl+1};
        unsigned prior=errors;
        for(unsigned st=0;st<5;++st){
            unsigned start=starts[st];
            unsigned ordinal=((seed*20+op)*5+mode)*5+st;
            if(ordinal<EDGE_BEGIN || ordinal>EDGE_END)continue;
            if(start>evl || start>=8*vlenb || (mode==4 && op>=16)){++skips;continue;}
            for(unsigned i=0;i<1024;++i)input[i]=(uint8_t)(i*37+seed*71+3);
            for(unsigned i=0;i<1088;++i)output[i]=0x5b;
            unsigned long status=functions[op](input,output+32,start,mode);
            if((uint32_t)status || status>>32!=start)++errors;
            for(unsigned i=0;i<1088;++i){unsigned active=i>=32+start*bytes && i<32+n*vlenb;
                uint8_t wanted=active ? input[i-32]:0x5b;
                if(output[i]!=wanted){
#if DETAIL_BYTES
                    if(errors<12){text("RVV_WHOLE_BYTE op=");num(op);text(" mode=");num(mode);
                        text(" vstart=");num(start);text(" byte=");num(i);text(" expected=");num(wanted);
                        text(" actual=");num(output[i]);text("\n");}
#endif
                    ++errors;
                }}
            ++cases;
        }
        if(errors!=prior){text("RVV_WHOLE_DETAIL op=");num(op);text(" mode=");num(mode);text(" errors=");num(errors-prior);text("\n");}
    }
    text(errors ? "RVV_WHOLE_FAIL cases=":"RVV_WHOLE_PASS cases=");num(cases);text(" skips=");num(skips);text(" errors=");num(errors);text("\n");
    return errors ? 1 : 0;
}
