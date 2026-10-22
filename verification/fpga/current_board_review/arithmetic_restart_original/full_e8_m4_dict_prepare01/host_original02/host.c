#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "case.c"
#ifndef PACKED_CASE
#include "dictionary.h"
#include "packed.h"
#endif
#include "host_fixture.h"
static unsigned calls,mutation,injected;
static void require_host(int yes,const char *why) {
    if(!yes){fprintf(stderr,"HOST_BLOCK call=%u %s\n",calls+1,why);exit(90);}
}
long replay_write(long n,long fd,long data,long count) {
    require_host(n==64 && fd==1,"console syscall");
    return (long)fwrite((void *)data,1,(size_t)count,stdout);
}
unsigned long capacity(void){return 512;}
static unsigned long emulate(unsigned op,const word *x,const word *y,word *dst,
    unsigned long vl,unsigned long cap,const uint8_t *predicate,unsigned long start) {
    require_host(calls<4095,"duplicate call");
    const struct fixture_row *r=&fixture_rows[calls];
    require_host(op==r->op && vl==r->vl && start==r->start && cap==512,"sequence/params");
    require_host(x==a && y==b && dst==out+1 && predicate==mask,"source pointers");
    for(unsigned i=0;i<512;++i){
        require_host(x[i]==fixture_a[r->seed][i] && y[i]==fixture_b[r->seed][i],"every input byte");
    }
    for(unsigned i=512;i<1024;++i)require_host(a[i]==0 && b[i]==0,"unused input footprint");
    for(unsigned i=0;i<128;++i)require_host(predicate[i]==physical_masks[r->mode][i],"full physical predicate");
    for(unsigned i=0;i<514;++i)require_host(out[i]==91,"fresh exact514");
    for(unsigned i=514;i<1026;++i)require_host(out[i]==0,"initialization overrun");
    unsigned packed=0;word reduced=y[0];
    if(op==22)for(unsigned i=0;i<vl;++i)if(selected(r->mode,i))reduced+=x[i];
    for(unsigned i=0;i<512;++i){
        word expected=91;
        if(op==22){if(i==0 && vl)expected=reduced;}
        else if(op==23){
            while(packed<vl && !selected(r->mode,packed))++packed;
            if(packed<vl)expected=x[packed++];
        }else if(i<vl && i>=start && selected(r->mode,i)){
            if(op<19)expected=value(op,x[i],y[i]);
            else if(op==19){if(i>=2)expected=x[i-2];}
            else if(op==20)expected=i+2<cap?x[i+2]:0;
            else if(op==21)expected=y[i]<cap?x[y[i]]:0;
            else if(op==24)expected=x[i];
        }
        unsigned pos=i+1,group=pos/8,shift=8*(pos%8);
        word independent=(word)(expected_dictionary[expected_indices[calls][group]]>>shift);
        require_host(expected==independent,"original C vs Python/dictionary every position");
        dst[i]=independent;
    }
    require_host((word)expected_dictionary[expected_indices[calls][0]]==91 &&
        (word)(expected_dictionary[expected_indices[calls][64]]>>8)==91,"both dictionary guards");
    unsigned long returned=0;
    if(mutation && !injected){
        unsigned pos=0,found=0;
        for(unsigned i=0;i<512 && !found;++i){
            int choose=mutation==1?(i>=start && i<vl && selected(r->mode,i) && op==0):
                mutation==2?(i<start && start<vl && op==0):
                mutation==3?(i<vl && !selected(r->mode,i) && op==0):
                mutation==4?(i>=vl && vl>0 && op==0):0;
            if(choose){pos=i+1;found=1;}
        }
        if(mutation==5){pos=0;found=1;}
        if(mutation==6){pos=513;found=1;}
        if(mutation==7){returned=UINT64_C(1)<<40;found=1;}
        if(found){if(mutation!=7)out[pos]^=1;injected=1;}
    }
    ++calls;return returned;
}
#define OP(N) unsigned long op_##N(const word*x,const word*y,word*d,unsigned long vl,unsigned long cap,const uint8_t*m,unsigned long s){return emulate(N,x,y,d,vl,cap,m,s);}
OP(0) OP(1) OP(2) OP(3) OP(4) OP(5) OP(6) OP(7) OP(8) OP(9)
OP(10) OP(11) OP(12) OP(13) OP(14) OP(15) OP(16) OP(17) OP(18) OP(19)
OP(20) OP(21) OP(22) OP(23) OP(24)
int main(int argc,char **argv){
    mutation=argc>1?(unsigned)strtoul(argv[1],0,10):0;
    uint8_t raw[530];memset(raw,0xa7,sizeof(raw));
    initialize_output(raw+1);
    require_host(raw[0]==0xa7 && raw[515]==0xa7,"misaligned memcpy footprint");
    for(unsigned i=1;i<=514;++i)require_host(raw[i]==91,"misaligned full fill");
    require_host(raw_word(raw+1)==UINT64_C(0x5b5b5b5b5b5b5b5b),"unaligned safe word");
    require_host(!packed_mismatch(raw+1,0),"full packed unaligned comparison");
    uint8_t physical[128];initialize_mask(physical,2);
    require_host(memcmp(physical,physical_masks[2],128)==0,"physical mask copy footprint");
    require_host(value(15,128,255)==128 && value(16,128,255)==0 &&
        value(15,0,0)==255 && value(16,128,0)==128,"division corner");
    int rc=arithmetic_main();
    require_host(calls==4095 && checks==4095 && elements==2096640,"complete scope/counters");
    require_host(mutation?injected && rc==1 && errors==1:rc==0 && errors==0,"original failure fallback");
    printf("HOST_FULL4095 positions=2096640 guards=8190 masks=524160 calls=%u injected=%u errors=%lu rc=%d\n",calls,injected,(unsigned long)errors,rc);
    return rc;
}
