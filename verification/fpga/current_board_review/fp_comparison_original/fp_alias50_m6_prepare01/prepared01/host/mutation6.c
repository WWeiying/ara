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
#include "fixtures.h"
static word a[1024],b[1024];
static uint8_t mask[128],output[130];
extern unsigned long capacity(void);
typedef unsigned long (*operation)(const void *,const void *,void *,unsigned long,
                                   unsigned long,const void *,unsigned long,unsigned long);
static operation functions[]={FUNCTIONS};
extern long replay_write(long,long,long,long);
#define syscall3 replay_write
static void text(const char *s) {long n=0;while(s[n])++n;syscall3(64,1,(long)s,n);}
static void num(uint64_t n) {char s[24];unsigned i=23;s[i]=0;do{s[--i]='0'+n%10;n/=10;}while(n);text(s+i);}
static unsigned bit(const uint8_t *p,unsigned i) {return (p[i/8]>>(i%8))&1;}
static unsigned lhs_index(unsigned seed,unsigned i) {return (i+seed+7*(seed/16))%16;}
static unsigned rhs_index(unsigned seed,unsigned i,unsigned op) {
    return op<4 ? (i*3+seed*5+seed/16)%16:seed%16;
}
int alias_v8_e16m8_prefix50_main(void) {
    unsigned cap=capacity(),errors=0,cases=0,details=0;
    if(!cap || cap>1024){text("RVV_FP_COMPARE_CAPACITY_FAIL\n");return 2;}
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
        for(unsigned i=0;i<cap;++i) {
            a[i]=inputs[lhs_index(seed,i)];
            b[i]=inputs[rhs_index(seed,i,op)];
        }
        for(unsigned i=0;i<130;++i)output[i]=0x5b;
        if(RESTART_COMPARISONS && !seed && !op && !mode && !sticky) {
            text("RVV_FP_COMPARE_TRIAL vl=");num(vl);text(" vstart=");num(start);text("\n");
            (void)0; /* Linux UART drain only. */
        }
        unsigned long status=functions[op](a,b,output+1,vl,cap,mask,start,sticky);
        if((uint32_t)status)++errors;
        for(unsigned i=0;i<cap;++i) {
            unsigned ai=lhs_index(seed,i),bi=rhs_index(seed,i,op);
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
        ++cases;
        if(cases==50)goto prefix_done;
    }
prefix_done:
    text(errors ? "RVV_FP_COMPARE_FAIL sew=":"RVV_FP_COMPARE_PASS sew=");num(SEW);
    text(" cases=");num(cases);text(" errors=");num(errors);text("\n");
    return errors ? 1:0;
}


#include <stdio.h>
#include <stdlib.h>
unsigned long capacity(void){return HOST_CAP;}
long replay_write(long n,long fd,long p,long len){if(n!=64||fd!=1)abort();return fwrite((void*)p,1,len,stdout);}
static unsigned calls;
static struct fixture independent(unsigned op,unsigned a,unsigned b){
    unsigned an=(a&0x7c00)==0x7c00 && (a&1023), bn=(b&0x7c00)==0x7c00 && (b&1023);
    unsigned sn=(an && !(a&512)) || (bn && !(b&512));
    unsigned eq=a==b || ((a&0x7fff)==0 && (b&0x7fff)==0);
    unsigned ka=(a&0x8000)?(a^0xffff):(a^0x8000), kb=(b&0x8000)?(b^0xffff):(b^0x8000);
    unsigned lt=!eq && ka<kb;
    unsigned flags=(op<2?sn:an||bn)?16:0;
    unsigned bit=an||bn ? op==1 : op==0?eq:op==1?!eq:op==2?lt:op==3?lt||eq:op==4?!lt&&!eq:!lt;
    return (struct fixture){bit,flags};
}
static unsigned long emulate(unsigned op,const void*aa,const void*bb,void*oo,unsigned long vl,unsigned long cap,const void*mm,unsigned long start,unsigned long sticky){
    const word *a=aa,*b=bb;const unsigned char *m=mm;unsigned char *o=oo;
    unsigned flags=sticky;
    if(DESTINATION_KIND==1 || DESTINATION_KIND==2){const word *p=DESTINATION_KIND==1?a:b;
        for(unsigned i=0;i<cap;++i){unsigned mask=1u<<(i%8),old=(p[i/SEW]>>(i%SEW))&1;
            o[i/8]=(o[i/8]&~mask)|(old<<(i%8));}}
    for(unsigned i=0;i<cap;++i){
        if(i>=start && i<vl && (UNMASKED_COMPARISONS || ((m[i/8]>>(i%8))&1))){
            struct fixture r=independent(op<4?op:op-4,a[i],b[op<4?i:0]);
            unsigned mask=1u<<(i%8);o[i/8]=(o[i/8]&~mask)|(r.bit<<(i%8));flags|=r.flags;
        } else if(HOST_MUTATION==6 && start<vl && i>=vl)o[i/8]|=1u<<(i%8);
    }
    ++calls;
    if(HOST_MUTATION==7 && calls==HOST_CALLS)o[(cap-1)/8]^=1u<<((cap-1)%8);
    if(HOST_MUTATION==8 && calls==HOST_CALLS)o[(cap+7)/8]^=1;
    if(HOST_MUTATION==9 && calls==1)o[0]^=1;
    if(HOST_MUTATION==10 && calls==HOST_CALLS-1)o[1]^=8;
    if(calls==HOST_CALLS){
        if(HOST_MUTATION==1)o[start/8]^=1u<<(start%8);
        if(HOST_MUTATION==2)flags^=16;
        if(HOST_MUTATION==3)o[0]^=1;
        if(HOST_MUTATION==4)o[-1]^=1;
    }
    return ((unsigned long)flags<<32) | (HOST_MUTATION==5 && calls==HOST_CALLS);
}

unsigned long op_0(const void*a,const void*b,void*o,unsigned long vl,unsigned long cap,const void*m,unsigned long start,unsigned long flags){return emulate(0,a,b,o,vl,cap,m,start,flags);}
unsigned long op_1(const void*a,const void*b,void*o,unsigned long vl,unsigned long cap,const void*m,unsigned long start,unsigned long flags){return emulate(1,a,b,o,vl,cap,m,start,flags);}
unsigned long op_2(const void*a,const void*b,void*o,unsigned long vl,unsigned long cap,const void*m,unsigned long start,unsigned long flags){return emulate(2,a,b,o,vl,cap,m,start,flags);}
unsigned long op_3(const void*a,const void*b,void*o,unsigned long vl,unsigned long cap,const void*m,unsigned long start,unsigned long flags){return emulate(3,a,b,o,vl,cap,m,start,flags);}
unsigned long op_4(const void*a,const void*b,void*o,unsigned long vl,unsigned long cap,const void*m,unsigned long start,unsigned long flags){return emulate(4,a,b,o,vl,cap,m,start,flags);}
unsigned long op_5(const void*a,const void*b,void*o,unsigned long vl,unsigned long cap,const void*m,unsigned long start,unsigned long flags){return emulate(5,a,b,o,vl,cap,m,start,flags);}
unsigned long op_6(const void*a,const void*b,void*o,unsigned long vl,unsigned long cap,const void*m,unsigned long start,unsigned long flags){return emulate(6,a,b,o,vl,cap,m,start,flags);}
unsigned long op_7(const void*a,const void*b,void*o,unsigned long vl,unsigned long cap,const void*m,unsigned long start,unsigned long flags){return emulate(7,a,b,o,vl,cap,m,start,flags);}
unsigned long op_8(const void*a,const void*b,void*o,unsigned long vl,unsigned long cap,const void*m,unsigned long start,unsigned long flags){return emulate(8,a,b,o,vl,cap,m,start,flags);}
unsigned long op_9(const void*a,const void*b,void*o,unsigned long vl,unsigned long cap,const void*m,unsigned long start,unsigned long flags){return emulate(9,a,b,o,vl,cap,m,start,flags);}
int main(void){for(unsigned op=0;op<6;++op)for(unsigned a=0;a<16;++a)for(unsigned b=0;b<16;++b){struct fixture r=independent(op,inputs[a],inputs[b]);if(r.bit!=expected[op][a][b].bit || r.flags!=expected[op][a][b].flags)abort();}return alias_v8_e16m8_prefix50_main();}
