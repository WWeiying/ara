#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include "case.c"
#ifndef PACKED_CASE
#include "expected.h"
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
unsigned long capacity(void){return 64;}
static unsigned long emulate(unsigned op,const word *x,const word *y,word *dst,
    unsigned long vl,unsigned long cap,const uint8_t *predicate,unsigned long start) {
    require_host(calls<4095,"duplicate call");
    const struct fixture_row *r=&fixture_rows[calls];
    require_host(op==r->op && vl==r->vl && start==r->start && cap==64,"sequence/params");
    require_host(x==a && y==b && dst==out+1 && predicate==mask,"source pointers");
    for(unsigned i=0;i<64;++i){
        require_host(x[i]==fixture_a[r->seed][i] && y[i]==fixture_b[r->seed][i],"every input byte");
    }
    for(unsigned i=0;i<128;++i)require_host(predicate[i]==physical_masks[r->mode][i],"full physical predicate");
    for(unsigned i=0;i<66;++i)require_host(out[i]==91,"fresh exact66 typed005b");
    for(unsigned i=64;i<1024;++i)require_host(x[i]==0 && y[i]==0,"original unused input backing");
    for(unsigned i=66;i<1026;++i)require_host(out[i]==0,"original unused output backing");
    unsigned packed=0;word reduced=y[0];
    if(op==22)for(unsigned i=0;i<vl;++i)if(selected(r->mode,i))reduced+=x[i];
    for(unsigned i=0;i<64;++i){
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
        unsigned pos=i+1,shift=16*(pos%4);
        word independent=(word)(expected_words[calls][pos/4]>>shift);
        require_host(expected==independent,"original C vs Python/flat ROM every position");
        dst[i]=independent;
    }
    require_host((word)expected_words[calls][0]==91 &&
        (word)(expected_words[calls][16]>>16)==91,"both flat ROM guards");
    unsigned long returned=0;
    if(mutation && !injected){
        unsigned pos=0,found=0;
        for(unsigned i=0;i<64 && !found;++i){
            int choose=mutation==1?(i>=start && i<vl && selected(r->mode,i) && op==0):
                mutation==2?(i<start && start<vl && op==0):
                mutation==3?(i<vl && !selected(r->mode,i) && op==0):
                mutation==4?(i>=vl && vl>0 && op==0):0;
            if(choose){pos=i+1;found=1;}
        }
        if(mutation==5){pos=0;found=1;}
        if(mutation==6){pos=65;found=1;}
        if(mutation==7){returned=UINT64_C(1)<<40;found=1;}
        if(mutation==9){pos=64;found=1;}
        if(found){if(mutation!=7)out[pos]^=mutation==9?0x0100:1;injected=1;}
    }
    ++calls;return returned;
}
#define OP(N) unsigned long op_##N(const word*x,const word*y,word*d,unsigned long vl,unsigned long cap,const uint8_t*m,unsigned long s){return emulate(N,x,y,d,vl,cap,m,s);}
OP(0) OP(1) OP(2) OP(3) OP(4) OP(5) OP(6) OP(7) OP(8) OP(9)
OP(10) OP(11) OP(12) OP(13) OP(14) OP(15) OP(16) OP(17) OP(18) OP(19)
OP(20) OP(21) OP(22) OP(23) OP(24)
int main(int argc,char **argv){
    mutation=argc>1?(unsigned)strtoul(argv[1],0,10):0;
    if(mutation==8){volatile unsigned shift=64;volatile uint64_t one=1;printf("%lu\n",(unsigned long)(one<<shift));return 99;}
    uint8_t raw[148];memset(raw,0xa7,sizeof(raw));
    initialize_output(raw+1);
    require_host(raw[0]==0xa7 && raw[133]==0xa7,"misaligned memcpy footprint");
    for(unsigned i=1;i<=132;++i)require_host(raw[i]==((i&1)?91:0),"misaligned full fill");
    require_host(raw_word(raw+1)==UINT64_C(0x005b005b005b005b),"unaligned safe word");
    require_host(!packed_mismatch(raw+1,0),"full packed unaligned comparison");
    for(unsigned i=0;i<132;++i){
        raw[1+i]^=1;
        require_host(packed_mismatch(raw+1,0),"every output byte participates");
        raw[1+i]^=1;
    }
    long page=sysconf(_SC_PAGESIZE);
    require_host(page>132,"Host page size");
    uint8_t *mapping=mmap(0,2*(size_t)page,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    require_host(mapping!=MAP_FAILED && mprotect(mapping+page,(size_t)page,PROT_NONE)==0,"guard page");
    uint8_t *edge=mapping+page-132;
    initialize_output(edge);
    require_host(!packed_mismatch(edge,0),"exact tail must not cross protected page");
    require_host(munmap(mapping,2*(size_t)page)==0,"guard cleanup");
    uint8_t physical[128];initialize_mask(physical,2);
    require_host(memcmp(physical,physical_masks[2],128)==0,"physical mask copy footprint");
    require_host(value(15,32768,65535)==32768 && value(16,32768,65535)==0 &&
        value(15,0,0)==65535 && value(16,32768,0)==32768,"division corner");
    int rc=arithmetic_main();
    require_host(calls==4095 && checks==4095 && elements==262080,"complete scope/counters");
    require_host(mutation?injected && rc==1 && errors==1:rc==0 && errors==0,"original failure fallback");
    printf("HOST_FULL4095 positions=262080 guards=8190 masks=524160 calls=%u injected=%u errors=%lu rc=%d\n",calls,injected,(unsigned long)errors,rc);
    return rc;
}
