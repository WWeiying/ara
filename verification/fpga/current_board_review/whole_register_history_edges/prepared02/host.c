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
    unsigned long vlenb;vlenb=128; /* host-only ISA emulation */
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

#include <stdio.h>
#include <stdlib.h>
static int host_mutation;
static unsigned host_calls;
long replay_write(long n,long fd,long p,long z) {
    if(n!=64 || fd!=1)abort();
    return fwrite((void*)p,1,z,stdout);
}
static unsigned long emulate(unsigned op,const void *aa,void *oo,unsigned long start,unsigned long mode) {
    const unsigned char *a=aa; unsigned char *o=oo;
    unsigned n=1U<<(op<16?op/4:op-16), width=1U<<(op<16?op%4:mode);
    for(unsigned i=start*width;i<n*128;++i)o[i]=a[i];
    if(++host_calls==2) {
        if(host_mutation==1)o[-1]^=1;
        if(host_mutation==2)o[0]^=1;
        if(host_mutation==3)o[n*128-1]^=1;
        if(host_mutation==4)o[n*128]^=1;
        if(host_mutation==5)o[1055]^=1;
        if(host_mutation==6)return (start<<32)|1;
        if(host_mutation==7)return (start+1)<<32;
    }
    return start<<32;
}
unsigned long op_0(const void*a,void*o,unsigned long s,unsigned long m){return emulate(0,a,o,s,m);}
unsigned long op_1(const void*a,void*o,unsigned long s,unsigned long m){return emulate(1,a,o,s,m);}
unsigned long op_2(const void*a,void*o,unsigned long s,unsigned long m){return emulate(2,a,o,s,m);}
unsigned long op_3(const void*a,void*o,unsigned long s,unsigned long m){return emulate(3,a,o,s,m);}
unsigned long op_4(const void*a,void*o,unsigned long s,unsigned long m){return emulate(4,a,o,s,m);}
unsigned long op_5(const void*a,void*o,unsigned long s,unsigned long m){return emulate(5,a,o,s,m);}
unsigned long op_6(const void*a,void*o,unsigned long s,unsigned long m){return emulate(6,a,o,s,m);}
unsigned long op_7(const void*a,void*o,unsigned long s,unsigned long m){return emulate(7,a,o,s,m);}
unsigned long op_8(const void*a,void*o,unsigned long s,unsigned long m){return emulate(8,a,o,s,m);}
unsigned long op_9(const void*a,void*o,unsigned long s,unsigned long m){return emulate(9,a,o,s,m);}
unsigned long op_10(const void*a,void*o,unsigned long s,unsigned long m){return emulate(10,a,o,s,m);}
unsigned long op_11(const void*a,void*o,unsigned long s,unsigned long m){return emulate(11,a,o,s,m);}
unsigned long op_12(const void*a,void*o,unsigned long s,unsigned long m){return emulate(12,a,o,s,m);}
unsigned long op_13(const void*a,void*o,unsigned long s,unsigned long m){return emulate(13,a,o,s,m);}
unsigned long op_14(const void*a,void*o,unsigned long s,unsigned long m){return emulate(14,a,o,s,m);}
unsigned long op_15(const void*a,void*o,unsigned long s,unsigned long m){return emulate(15,a,o,s,m);}
unsigned long op_16(const void*a,void*o,unsigned long s,unsigned long m){return emulate(16,a,o,s,m);}
unsigned long op_17(const void*a,void*o,unsigned long s,unsigned long m){return emulate(17,a,o,s,m);}
unsigned long op_18(const void*a,void*o,unsigned long s,unsigned long m){return emulate(18,a,o,s,m);}
unsigned long op_19(const void*a,void*o,unsigned long s,unsigned long m){return emulate(19,a,o,s,m);}
int main(int argc,char**argv){host_mutation=argc>1?atoi(argv[1]):0;int r=whole_original_main();return host_calls==2?r:91;}
