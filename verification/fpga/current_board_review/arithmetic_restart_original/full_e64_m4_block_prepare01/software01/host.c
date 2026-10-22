#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
static unsigned calls, mutation, injected, setup_variant, monitoring;
static unsigned fp_order, fp_calls, fresh_count, read_count, mask_events;
static unsigned total_fp, total_fresh, total_reads, total_clear, total_bits;
static void fp_event(uint64_t *, uint64_t);
static int skip_fp(uint64_t *);
static int duplicate_fp(uint64_t *);
static void mask_event(unsigned, unsigned, const uint8_t *);
static int skip_clear(unsigned);
static int skip_bit(unsigned);
static int skip_fresh(unsigned);
static void fresh_event(uint64_t *, uint64_t);
static void read_event(const volatile uint64_t *, uint64_t);
#include "host_case.c"
#ifndef PACKED_CASE
#include "packed_output.h"
#include "mask_setup.h"
#endif
#include "dictionary.h"
#include "host_fixture.h"
static uint64_t expected_words[5985][66];
static void need(int yes, const char *why) {
    if (!yes) { fprintf(stderr,"HOST_BLOCK call=%u %s\n",calls+1,why); exit(90); }
}
static void fp_event(uint64_t *p, uint64_t value) {
    if (!monitoring) return;
    unsigned bank = (uintptr_t)p >= (uintptr_t)b && (uintptr_t)p < (uintptr_t)(b+64);
    uint64_t *base = bank ? b : a;
    need((uintptr_t)p >= (uintptr_t)base && (uintptr_t)p < (uintptr_t)(base+64),"FP address range");
    unsigned index = (unsigned)(((uintptr_t)p-(uintptr_t)base)/8);
    need(*p==value && fp_order==2*index+bank,"FP ordered exact actual store");
    ++fp_order; ++total_fp;
}
static int skip_fp(uint64_t *p) {
    if (!monitoring) return 0;
    return (calls==1366 && ((setup_variant==1 && p==a+63) ||
                           (setup_variant==2 && p==b+63))) ||
           (setup_variant==5 && calls==1365);
}
static int duplicate_fp(uint64_t *p) {
    return monitoring && setup_variant==4 && calls==1366 && p==a+63;
}
static int skip_clear(unsigned offset) {
    return monitoring && setup_variant==7 && calls==0 && offset==120;
}
static int skip_bit(unsigned index) {
    return monitoring && setup_variant==8 && calls==0 && index==63;
}
static int skip_fresh(unsigned index) {
    return monitoring && calls==1 && ((setup_variant==10 && index==65) ||
           (setup_variant==11 && index==0) || (setup_variant==12 && index==32));
}
static void fresh_event(uint64_t *p, uint64_t value) {
    if (!monitoring) return;
    need(fresh_count<66 && p==out+fresh_count && value==91 && *p==91,"every fresh output/guard store ordered");
    ++fresh_count; ++total_fresh;
}
static void read_event(const volatile uint64_t *p, uint64_t value) {
    if (!monitoring) return;
    need(read_count<66 && p==out+read_count && value==*p,"every actual output word read ordered");
    ++read_count; ++total_reads;
}
static void mask_event(unsigned kind, unsigned index, const uint8_t *p) {
    if (!monitoring) return;
    need(calls<5985 && fixture_rows[calls].si==0,"mask phase/group");
    unsigned mode=fixture_rows[calls].mode;
    if (mask_events<16) {
        need(kind==0 && index==8*mask_events,"all16 ordered clear chunks");
        for (unsigned j=0;j<8;++j) need(p[index+j]==0,"actual clear value");
        ++total_clear;
    } else {
        unsigned ordinal=mask_events-16, seen=0, wanted=64;
        for (unsigned i=0;i<64;++i) if(selected(mode,i)) { if(seen++==ordinal){wanted=i;break;} }
        need(kind==1 && index==wanted,"original cumulative selected SB order");
        for (unsigned byte=0;byte<128;++byte) {
            unsigned v=0;
            for(unsigned bit=0;bit<8;++bit)
                if(byte*8+bit<=index && selected(mode,byte*8+bit)) v|=1u<<bit;
            need(p[byte]==v,"actual intermediate mask state");
        }
        ++total_bits;
    }
    ++mask_events;
}
long replay_write(long n,long fd,long p,long count) {
    need(n==64 && fd==1,"console service");
    return (long)fwrite((void *)p,1,(size_t)count,stdout);
}
unsigned long capacity(void) { return 64; }
static unsigned long emulate(unsigned op,const word *x,const word *y,word *dst,
    unsigned long vl,unsigned long cap,const uint8_t *predicate,unsigned long start) {
    need(calls<5985,"extra call");
    const struct fixture_row *r=&fixture_rows[calls];
    need(op==r->op && vl==r->vl && start==r->start && cap==64,"original order/arguments");
    need(x==a && y==b && dst==out+1 && predicate==mask,"original pointers");
#ifdef PACKED_CASE
    need(read_count==(calls?66u:0u),"previous complete66 output reads"); read_count=0;
#endif
    need(fresh_count==66,"full fresh66 stores even equal old values");fresh_count=0;
    for(unsigned i=0;i<64;++i) {
        uint64_t ax=op>=25?fp_inputs[(i+r->seed)%8]:fixture_a[r->seed][i];
        uint64_t by=op>=25?fp_inputs[(3*i+r->seed)%8]:fixture_b[r->seed][i];
        need(x[i]==ax && y[i]==by,"all input words and next-seed RNG");
    }
    need(fp_order==(op>=25?128u:0u),"full128 ordered FP stores on every call including VL0");fp_order=0;
    if(op>=25) ++fp_calls;
    unsigned bits=r->mode==0?64:r->mode==1?32:9;
    need(mask_events==(r->si==0?16+bits:0),"complete mask group receipts");mask_events=0;
    for(unsigned i=0;i<128;++i) {
        unsigned v=0;
        for(unsigned bit=0;bit<8;++bit)if(i*8+bit<64 && selected(r->mode,i*8+bit))v|=1u<<bit;
        need(predicate[i]==v,"physical128 mask exact");
    }
    for(unsigned i=0;i<66;++i)need(out[i]==91,"fresh typed64 sentinel/guard");
    for(unsigned i=64;i<1024;++i)need(!a[i]&&!b[i],"unused input backing");
    for(unsigned i=66;i<1026;++i)need(!out[i],"unused output backing");
    unsigned packed=0;word reduced=y[0];
    if(op==22)for(unsigned i=0;i<vl;++i)if(selected(r->mode,i))reduced+=x[i];
    for(unsigned i=0;i<64;++i) {
        word gold=91;
        if(op==22) {if(i==0&&vl)gold=reduced;}
        else if(op==23) {while(packed<vl&&!selected(r->mode,packed))++packed;if(packed<vl)gold=x[packed++];}
        else if(i>=start&&i<vl&&selected(r->mode,i)) {
            if(op<19)gold=value(op,x[i],y[i]);
            else if(op==19){if(i>=2)gold=x[i-2];}
            else if(op==20)gold=i+2<cap?x[i+2]:0;
            else if(op==21)gold=y[i]<cap?x[y[i]]:0;
            else if(op==24)gold=x[i];
            else gold=fp_expected[op-25][((i+r->seed)%8)*8+(3*i+r->seed)%8];
        }
        need(gold==expected_words[calls][i+1],"actual original C oracle versus independent complete model");
        dst[i]=gold;
    }
    need(expected_words[calls][0]==91 && expected_words[calls][65]==91,"both typed64 guards");
    unsigned long returned=0;
    if(mutation&&!injected) {
        unsigned pos=0,found=0;uint64_t flip=1;
        for(unsigned i=0;i<64&&!found;++i) {
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
        if(mutation==6){pos=65;found=1;flip=UINT64_C(0x8000000000000000);}
        if(mutation==7){returned=1UL<<40;found=1;}
        if(mutation==11){pos=64;found=1;flip=UINT64_C(0x8000000000000000);}
        if(mutation==13){out[1]^=1;out[2]^=1;injected=1;}
        if(found){if(mutation!=7)out[pos]^=flip;injected=1;}
    }
    ++calls;
    if(calls<5985 && fixture_rows[calls].si==0)memset(mask,0xa7,128);
    return returned;
}
#define OP(N) unsigned long op_##N(const word*x,const word*y,word*d,unsigned long v,unsigned long c,const uint8_t*m,unsigned long s){return emulate(N,x,y,d,v,c,m,s);}
OP(0) OP(1) OP(2) OP(3) OP(4) OP(5) OP(6) OP(7) OP(8) OP(9)
OP(10) OP(11) OP(12) OP(13) OP(14) OP(15) OP(16) OP(17) OP(18) OP(19)
OP(20) OP(21) OP(22) OP(23) OP(24) OP(25) OP(26) OP(27) OP(28) OP(29)
OP(30) OP(31) OP(32) OP(33) OP(34)
int main(int argc,char **argv) {
    (void)skip_fp; (void)duplicate_fp;
    mutation=argc>1?(unsigned)strtoul(argv[1],0,10):0;
    setup_variant=argc>2?(unsigned)strtoul(argv[2],0,10):0;
    FILE *f=fopen(GOLD_PATH,"rb");need(f!=NULL,"full gold file");
    need(fread(expected_words,1,sizeof(expected_words),f)==sizeof(expected_words) && fgetc(f)==EOF,"exact full gold size");fclose(f);
    uint64_t raw[68];memset(raw,0xa7,sizeof(raw));
    e64m4_initialize_output(raw+1);
    need(raw[0]==UINT64_C(0xa7a7a7a7a7a7a7a7) && raw[67]==raw[0],"aligned528B outer guards");
    need(!e64m4_packed_mismatch(raw+1,0),"typed64 fill/read");
    unsigned char *bytes=(unsigned char *)(raw+1);
    for(unsigned i=0;i<528;++i){bytes[i]^=1;need(e64m4_packed_mismatch(raw+1,0),"every one of528 bytes participates");bytes[i]^=1;}
    raw[2]^=1;raw[3]^=1;need(e64m4_packed_mismatch(raw+1,0),"equal XOR faults do not cancel");raw[2]^=1;raw[3]^=1;
    long page=sysconf(_SC_PAGESIZE);need(page>528,"page size");
    unsigned char *p=mmap(0,2*(size_t)page,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    need(p!=MAP_FAILED && !mprotect(p+page,(size_t)page,PROT_NONE),"protection page");
    e64m4_initialize_output((uint64_t *)(p+page-528));
    need(!e64m4_packed_mismatch((uint64_t *)(p+page-528),0),"no rounded read beyond final16B");
    for(unsigned mode=0;mode<3;++mode) {
        unsigned char dirty[130];memset(dirty,0xa7,sizeof(dirty));
        e64m4_initialize_mask(dirty+1,mode);
        need(dirty[0]==0xa7 && dirty[129]==0xa7,"mask128 exact outer guards");
        memset(p+page-128,0xa7,128);e64m4_initialize_mask(p+page-128,mode);
        for(unsigned j=0;j<128;++j)need(p[page-128+j]==dirty[1+j],"all dirty mask bytes exact through protected boundary");
    }
    need(!munmap(p,2*(size_t)page),"unmap");
    need(value(15,UINT64_C(0x8000000000000000),UINT64_MAX)==UINT64_C(0x8000000000000000) && value(16,UINT64_C(0x8000000000000000),UINT64_MAX)==0,"signed division corner");
    need(value(5,1,63)==(UINT64_C(1)<<63) && value(5,1,64)==1,"masked shifts63/64");
    if(mutation==12){volatile unsigned shift=64;volatile uint64_t one=1;printf("%lu\n",(unsigned long)(one<<shift));return 99;}
    memset(mask,setup_variant==7?0:0xa7,128);monitoring=1;
    int rc=arithmetic_main();
#ifdef PACKED_CASE
    need(read_count==66 && total_reads==395010,"full66 observed reads per call");
#endif
    need(total_clear==35280 && total_bits==77175,"complete mask event counts");
    need(total_fresh==395010 && total_fp==241920,"full fresh/FP writes");
    need(calls==5985 && checks==5985 && elements==383040 && fp_calls==1890,"complete original scope");
    need(mutation?injected&&rc==1&&errors==(mutation==13?2u:1u):rc==0&&!errors,"full original fallback exact errors");
    printf("HOST_FULL5985 results=383040 guards=11970 fp_calls=1890 fp_stores=241920 calls=%u injected=%u errors=%lu rc=%d\n",calls,injected,(unsigned long)errors,rc);
    return rc;
}
