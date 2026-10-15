#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
typedef uint16_t word;
struct fixture {unsigned bit,flags;};
#include "fixtures.h"
static unsigned calls, mutation;
static FILE *record;
extern int alias_v8_e16m8_prefix682_main(void);
unsigned long capacity(void) {return 512;}
long replay_write(long nr,long fd,long data,long size) {
    assert(nr==64 && fd==1);
    return fwrite((void *)data,1,size,stdout);
}
static unsigned long operation(unsigned op,const void *aa,const void *bb,void *out,
        unsigned long vl,unsigned long cap,const void *mask,unsigned long start,unsigned long sticky) {
    const uint16_t *a=aa,*b=bb;
    uint8_t *o=out;
    uint64_t params[]={calls,op,vl,cap,start,sticky};
    assert(cap==512 && start==0);
    assert(fwrite(params,sizeof(params),1,record)==1);
    assert(fwrite(a,1024,1,record)==1 && fwrite(b,1024,1,record)==1);
    assert(fwrite(mask,128,1,record)==1 && fwrite(o-1,130,1,record)==1);
    unsigned flags=sticky;
    for(unsigned i=0;i<512;++i) {
        unsigned ai=16,bi=16;
        for(unsigned k=0;k<16;++k) {
            if(inputs[k]==a[i])ai=k;
            if(inputs[k]==b[op<4?i:0])bi=k;
        }
        assert(ai<16 && bi<16);
        struct fixture f=expected[op<4?op:op-4][ai][bi];
        unsigned old=(a[i/16]>>(i%16))&1;
        unsigned bit=i<vl?f.bit:old;
        o[i/8]=(o[i/8]&~(1u<<(i%8)))|(bit<<(i%8));
        if(i<vl)flags|=f.flags;
    }
    unsigned long status=(unsigned long)flags<<32;
    if(calls==0) {
        if(mutation==1)o[0]^=1; /* VL0 preserved alias bit. */
        if(mutation==2)o[-1]^=1;
        if(mutation==3)o[64]^=1;
        if(mutation==4)status^=1UL<<36;
        if(mutation==5)status|=1;
    }
    if(calls==8 && mutation==6)o[0]^=1; /* Active result bit, VL1. */
    ++calls;
    return status;
}
#define OP(N) unsigned long op_##N(const void*a,const void*b,void*c,unsigned long d,unsigned long e,const void*f,unsigned long g,unsigned long h){return operation(N,a,b,c,d,e,f,g,h);}
OP(0) OP(1) OP(2) OP(3) OP(4) OP(5) OP(6) OP(7) OP(8) OP(9)
int main(int argc,char **argv) {
    assert(argc==3);
    mutation=strtoul(argv[1],0,10);
    record=fopen(argv[2],"wbx"); assert(record);
    int rc=alias_v8_e16m8_prefix682_main();
    assert(calls==682 && fclose(record)==0);
    return rc;
}
