#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stdint.h>
static unsigned calls, mutation, injected, fp_writes[2][32], fp_calls;
static void fp_store(unsigned bank, unsigned index, uint64_t value);
#include "host_case.c"
#ifndef PACKED_CASE
#include "dictionary.h"
#include "packed.h"
#include "mask_clear.h"
#endif
#include "host_fixture.h"
#include "host_expected.h"
static void need(int yes,const char *why) {
    if(!yes){fprintf(stderr,"HOST_BLOCK call=%u %s\n",calls+1,why);exit(90);}
}
static void fp_store(unsigned bank,unsigned index,uint64_t value) {
    need(bank<2 && index<32,"fresh receipt range");
    need(value==(bank?b[index]:a[index]),"receipt actual store value");
    ++fp_writes[bank][index];
}
long replay_write(long n,long fd,long p,long count) {
    need(n==64 && fd==1,"console service");
    return (long)fwrite((void *)p,1,(size_t)count,stdout);
}
unsigned long capacity(void){return 32;}
static unsigned long emulate(unsigned op,const word *x,const word *y,word *dst,
    unsigned long vl,unsigned long cap,const uint8_t *predicate,unsigned long start) {
    need(calls<5985,"extra call");
    const struct fixture_row *r=&fixture_rows[calls];
    need(op==r->op && vl==r->vl && start==r->start && cap==32,"original complete order/args");
    need(x==a && y==b && dst==out+1 && predicate==mask,"actual pointers");
    for(unsigned i=0;i<32;++i){
        uint64_t ax=op>=25?fp_inputs[(i+r->seed)%8]:fixture_a[r->seed][i];
        uint64_t by=op>=25?fp_inputs[(3*i+r->seed)%8]:fixture_b[r->seed][i];
        need(x[i]==ax && y[i]==by,"every input and next-seed RNG");
        need(fp_writes[0][i]==(op>=25) && fp_writes[1][i]==(op>=25),"every FP call fresh stores, even equal old value");
        fp_writes[0][i]=fp_writes[1][i]=0;
    }
    if(op>=25)++fp_calls;
    for(unsigned i=0;i<128;++i){
        unsigned v=0;
        for(unsigned bit=0;bit<8;++bit)if(i*8+bit<32 && selected(r->mode,i*8+bit))v|=1u<<bit;
        need(predicate[i]==v,"physical128 predicate exact");
    }
    for(unsigned i=0;i<34;++i)need(out[i]==91,"fresh typed sentinel");
    for(unsigned i=32;i<1024;++i)need(!a[i]&&!b[i],"unused input backing");
    for(unsigned i=34;i<1026;++i)need(!out[i],"unused output backing");
    unsigned packed=0;word reduced=y[0];
    if(op==22)for(unsigned i=0;i<vl;++i)if(selected(r->mode,i))reduced+=x[i];
    for(unsigned i=0;i<32;++i){
        word gold=91;
        if(op==22){if(i==0&&vl)gold=reduced;}
        else if(op==23){while(packed<vl&&!selected(r->mode,packed))++packed;if(packed<vl)gold=x[packed++];}
        else if(i>=start&&i<vl&&selected(r->mode,i)){
            if(op<19)gold=value(op,x[i],y[i]);
            else if(op==19){if(i>=2)gold=x[i-2];}
            else if(op==20)gold=i+2<cap?x[i+2]:0;
            else if(op==21)gold=y[i]<cap?x[y[i]]:0;
            else if(op==24)gold=x[i];
            else gold=fp_expected[op-25][((i+r->seed)%8)*8+(3*i+r->seed)%8];
        }
        unsigned p=i+1;
        word independent=expected_words[calls][p];
        need(gold==independent,"original C vs exact table/model every64bit result");
        dst[i]=independent;
    }
    need(expected_words[calls][0]==91 && expected_words[calls][33]==91,"both64bit guards");
    unsigned long returned=0;
    if(mutation&&!injected){
        unsigned pos=0,found=0;uint64_t flip=1;
        for(unsigned i=0;i<32&&!found;++i){
            int choose=mutation==1?(op==0&&i>=start&&i<vl&&selected(r->mode,i)):
                mutation==2?(op==0&&i<start&&start<vl):
                mutation==3?(op==0&&i<vl&&!selected(r->mode,i)):
                mutation==4?(op==0&&i>=vl&&vl>0):
                mutation==8?(op>=25&&dst[i]==UINT64_C(0x8000000000000000)):
                mutation==9?(op>=25&&dst[i]==UINT64_C(0x7ff8000000000000)):
                mutation==10?(op>=25&&i>=start&&i<vl&&selected(r->mode,i)):0;
            if(choose){pos=i+1;found=1;if(mutation==8)flip=UINT64_C(0x8000000000000000);}
        }
        if(mutation==5){pos=0;found=1;flip=UINT64_C(0x8000000000000000);}
        if(mutation==6){pos=33;found=1;flip=UINT64_C(0x8000000000000000);}
        if(mutation==7){returned=1UL<<40;found=1;}
        if(mutation==11){pos=32;found=1;flip=UINT64_C(0x8000000000000000);}
        if(found){if(mutation!=7)out[pos]^=flip;injected=1;}
    }
    ++calls;
    if(calls<5985 && (fixture_rows[calls].seed!=r->seed || fixture_rows[calls].op!=r->op || fixture_rows[calls].vl!=r->vl || fixture_rows[calls].mode!=r->mode))memset(mask,0xa7,128);
    return returned;
}
#define OP(N) unsigned long op_##N(const word*x,const word*y,word*d,unsigned long v,unsigned long c,const uint8_t*m,unsigned long s){return emulate(N,x,y,d,v,c,m,s);}
OP(0) OP(1) OP(2) OP(3) OP(4) OP(5) OP(6) OP(7) OP(8) OP(9)
OP(10) OP(11) OP(12) OP(13) OP(14) OP(15) OP(16) OP(17) OP(18) OP(19)
OP(20) OP(21) OP(22) OP(23) OP(24) OP(25) OP(26) OP(27) OP(28) OP(29)
OP(30) OP(31) OP(32) OP(33) OP(34)
int main(int argc,char **argv) {
    mutation=argc>1?(unsigned)strtoul(argv[1],0,10):0;
    unsigned char dirty[130];memset(dirty,0xa7,sizeof(dirty));
    initialize_mask_zero(dirty+1);
    need(dirty[0]==0xa7 && dirty[129]==0xa7,"mask128 exact unaligned guards");
    for(unsigned i=1;i<=128;++i)need(!dirty[i],"all128 mask bytes cleared");
    unsigned char raw[274];memset(raw,0xa7,sizeof(raw));
    initialize_output((void *)(raw+1));
    need(raw[0]==0xa7 && raw[273]==0xa7,"unaligned exact272 outer sentinels");
    need(!packed_mismatch((void *)(raw+1),0),"typed unaligned fill/read");
    for(unsigned i=0;i<272;++i){raw[1+i]^=1;need(packed_mismatch((void *)(raw+1),0),"every byte participates");raw[1+i]^=1;}
    long page=sysconf(_SC_PAGESIZE);need(page>272,"page size");
    unsigned char *p=mmap(0,2*(size_t)page,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    need(p!=MAP_FAILED && !mprotect(p+page,(size_t)page,PROT_NONE),"guard page");
    initialize_output((void *)(p+page-272));
    need(!packed_mismatch((void *)(p+page-272),0),"no roundup beyond272");
    memset(p+page-128,0xa7,128);initialize_mask_zero(p+page-128);
    for(unsigned i=0;i<128;++i)need(!p[page-128+i],"mask128 ends at protected page");
    need(!munmap(p,2*(size_t)page),"unmap");
    need(value(15,UINT64_C(0x8000000000000000),UINT64_MAX)==UINT64_C(0x8000000000000000) && value(16,UINT64_C(0x8000000000000000),UINT64_MAX)==0,"signed division corner");
    if(mutation==12){volatile unsigned shift=64;volatile uint64_t x=1;printf("%lu\n",(unsigned long)(x<<shift));return 99;}
    need(value(5,1,63)==(UINT64_C(1)<<63) && value(5,1,64)==1,"masked shifts63/64");
    int rc=arithmetic_main();
    need(calls==5985 && checks==5985 && elements==191520 && fp_calls==1890,"complete scope");
    need(mutation?injected&&rc==1&&errors==1:rc==0&&!errors,"full original fallback exact errors");
    printf("HOST_FULL5985 results=191520 guards=11970 fp_calls=1890 fp_stores=120960 calls=%u injected=%u errors=%lu rc=%d\n",calls,injected,(unsigned long)errors,rc);
    return rc;
}
