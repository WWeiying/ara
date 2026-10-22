#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
static unsigned calls, fault, injected, running, fp_order, fp_inputs_seen;
static unsigned mask_pos, init_pos, fp_calls, total_fp, total_sb, total_clear;
static unsigned cache_reads, cache_gold, cache_ids, full_reads, full_gold, full_ids;
static unsigned block_no, block_word, need_gold, last_id, current_id, previous_call;
static unsigned full_hits, full_misses;
static const unsigned char *actual_base;
static uint8_t shadow_mask[128];
static uint32_t *gold;
static void need(int,const char *);
static void fp_event(uint32_t *,uint32_t);
static void input_event(unsigned,uint32_t);
static void clear_event(unsigned,const uint8_t *);
static void selected_event(unsigned,uint8_t);
static void init_event(unsigned,const void *);
static void cache_begin(const void *,const uint16_t *);
static void id_event(unsigned,unsigned);
static void gold_event(const uint64_t *,uint64_t);
static void tag_event(unsigned,unsigned);
static void actual_event(const void *,uint64_t);
static void cache_end(void);
#include "host_case.c"
#ifndef PACKED_CASE
#include "packed_cache.h"
#endif
#include "fixture.h"

static void need(int yes,const char *why) {
    if(!yes){fprintf(stderr,"HOST_BLOCK call=%u fault=%u %s\n",calls+1,fault,why);exit(90);}
}
static void input_event(unsigned i,uint32_t value) {
    if(!running)return;
    need(i==fp_inputs_seen && value==fp_inputs[i],"eight fresh ordered immutable FP input reads");
    ++fp_inputs_seen;
}
static void fp_event(uint32_t *dst,uint32_t value) {
    if(!running)return;
    unsigned bank=2,index=128;
    for(unsigned i=0;i<128;++i){if(dst==a+i){bank=0;index=i;}if(dst==b+i){bank=1;index=i;}}
    need(bank<2 && index<128,"FP actual destination");
    need(fp_order==2*index+bank && *dst==value,"every FP a,b store order/value");
#ifdef PACKED_CASE
    need(fp_inputs_seen==8,"all fresh FP input reads before writes");
#endif
    ++fp_order;++total_fp;
}
static void clear_event(unsigned offset,const uint8_t *p) {
    if(!running)return;
    need(calls<5985 && fixture[calls].si==0,"clear belongs to first group tuple");
    need(mask_pos<16 && offset==8*mask_pos,"sixteen ordered full clears");
    for(unsigned i=0;i<8;++i){need(p[offset+i]==0,"cleared actual byte");shadow_mask[offset+i]=0;}
    ++mask_pos;++total_clear;
}
static void selected_event(unsigned offset,uint8_t value) {
    if(!running)return;
    need(mask_pos>=16 && fixture[calls].si==0,"all clear events before selected SB");
    unsigned ordinal=mask_pos-16,seen=0,wanted=128;
    for(unsigned i=0;i<128;++i)if(selected(fixture[calls].mode,i)){if(seen++==ordinal){wanted=i;break;}}
    need(wanted<128 && offset==wanted/8,"selected SB actual address/order");
    shadow_mask[offset]|=(uint8_t)(1u<<(wanted%8));
    need(value==shadow_mask[offset] && mask[offset]==value,"cumulative SB actual value");
    need(!memcmp(mask,shadow_mask,128),"whole mask including upper112 bytes");
    ++mask_pos;++total_sb;
}
static void init_event(unsigned offset,const void *p) {
    if(!running)return;
#ifdef PACKED_CASE
    need(offset==8*init_pos && init_pos<65,"all ordered output SD even equal old value");
    uint64_t v;memcpy(&v,(const unsigned char *)p+offset,8);
    need(v==UINT64_C(0x0000005b0000005b),"typed sentinel SD");
#else
    need(offset==4*init_pos && init_pos<130,"all original output word stores");
    uint32_t v;memcpy(&v,(const unsigned char *)p+offset,4);need(v==91,"original sentinel");
#endif
    ++init_pos;
}
static void cache_begin(const void *p,const uint16_t *ids) {
    actual_base=p;cache_reads=cache_gold=cache_ids=0;block_no=block_word=0;need_gold=0;last_id=65536;
    if(running){need(calls>0 && ids==e32m4_expected_ids[calls-1],"call-specific ID row");previous_call=calls;}
}
static void id_event(unsigned n,unsigned id) {
    need(n==cache_ids && n<9 && id<2252,"nine ordered exact IDs");
    if(running)need(id==e32m4_expected_ids[calls-1][n],"actual ID vs immutable row");
    need(n==0 || cache_reads==8*n,"all preceding actual reads before next ID");
    block_no=n;block_word=0;current_id=id;
    need_gold=n==8?1:(n==0 || id!=last_id?8:0);
    if(running && n<8){if(need_gold)++full_misses;else ++full_hits;}
    ++cache_ids;if(running)++full_ids;
}
static void gold_event(const uint64_t *p,uint64_t value) {
    need(need_gold>0,"no refill on same-ID hit");
    unsigned k=block_no==8?0:8-need_gold;
    need(p==e32m4_expected_blocks[current_id]+k && value==*p,"exact gold word/address, no stale value");
    --need_gold;++cache_gold;if(running)++full_gold;
}
static void tag_event(unsigned tag,unsigned requested) {
    need(tag==requested && requested==current_id && !need_gold,"complete refresh before exact tag");
    last_id=tag;
}
static void actual_event(const void *p,uint64_t value) {
    need(!need_gold && (block_no==8 || last_id==current_id),"mandatory first-fill and changed-ID refresh");
    need(p==actual_base+8*cache_reads && cache_reads<65,"all65 actual reads ordered, no caching/skipping");
    uint64_t actual;memcpy(&actual,p,8);need(value==actual,"actual data not expected substitution");
    ++cache_reads;++block_word;if(running)++full_reads;
}
static void cache_end(void) {
    need(cache_reads==65 && cache_ids==9 && !need_gold,"all65 reads even after error; complete tail8");
    if(running)need(calls==previous_call,"cache cannot cross helper calls");
}
long replay_write(long n,long fd,long p,long count) {
    need(n==64 && fd==1,"console service");return (long)fwrite((void *)p,1,(size_t)count,stdout);
}
unsigned long capacity(void){return 128;}
static unsigned long emulate(unsigned op,const word *x,const word *y,word *dst,
 unsigned long vl,unsigned long cap,const uint8_t *predicate,unsigned long start) {
    need(calls<5985,"full call membership");const struct row *r=fixture+calls;
    need(op==r->op && vl==r->vl && start==r->start && cap==128,"full original tuple/order");
    need(x==a && y==b && dst==out+1 && predicate==mask,"disjoint actual buffer ownership");
    for(unsigned i=0;i<128;++i){
        need(x[i]==(op>=25?fp_inputs[(i+r->seed)%8]:seed_a[r->seed][i]),"full a RNG/FP input");
        need(y[i]==(op>=25?fp_inputs[(3*i+r->seed)%8]:seed_b[r->seed][i]),"full b RNG/FP input");
    }
    need(fp_order==(op>=25?256u:0u),"complete fresh256 FP SW, including unchanged values");
    fp_order=fp_inputs_seen=0;if(op>=25)++fp_calls;
    unsigned n=r->mode==0?128:r->mode==1?64:18;
    need(mask_pos==(r->si==0?16+n:0),"all group clear and selected SB");mask_pos=0;
#ifdef PACKED_CASE
    need(init_pos==65,"full65 SD initialization");
#else
    need(init_pos==130,"full original initialization");
#endif
    init_pos=0;
    for(unsigned i=0;i<130;++i)need(out[i]==91,"full520B typed old destination");
    for(unsigned i=128;i<1024;++i)need(a[i]==0 && b[i]==0,"no input backing overflow");
    for(unsigned i=130;i<1026;++i)need(out[i]==0,"no output roundup/overflow");
    for(unsigned i=0;i<128;++i){unsigned v=0;for(unsigned k=0;k<8;++k)if(8*i+k<128 && selected(r->mode,8*i+k))v|=1u<<k;need(mask[i]==v,"physical128 predicate");}
    word reduced=y[0];unsigned packed=0;
    if(op==22)for(unsigned i=0;i<vl;++i)if(selected(r->mode,i))reduced+=x[i];
    for(unsigned i=0;i<128;++i){word expected=91;
        if(op==22){if(i==0&&vl)expected=reduced;}
        else if(op==23){while(packed<vl&&!selected(r->mode,packed))++packed;if(packed<vl)expected=x[packed++];}
        else if(i>=start&&i<vl&&selected(r->mode,i)){
            if(op<19)expected=value(op,x[i],y[i]);
            else if(op==19){if(i>=2)expected=x[i-2];}
            else if(op==20)expected=i+2<cap?x[i+2]:0;
            else if(op==21)expected=y[i]<cap?x[y[i]]:0;
            else if(op==24)expected=x[i];
            else expected=fp_expected[op-25][((i+r->seed)%8)*8+(3*i+r->seed)%8];
        }
        need(expected==gold[130*calls+i+1],"full original C vs independent model word");dst[i]=expected;
    }
    need(gold[130*calls]==91 && gold[130*calls+129]==91,"both original guards");
    unsigned long returned=0;
    if(fault && !injected && (fault<15 || fault==33)){
        unsigned pos=0,found=0,flip=1;
        for(unsigned i=0;i<128&&!found;++i){int choose=
            fault==1?(op==0&&i>=start&&i<vl&&selected(r->mode,i)):
            fault==2?(op==0&&i<start&&start<vl):
            fault==3?(op==0&&i<vl&&!selected(r->mode,i)):
            fault==4?(op==0&&i>=vl&&vl>0):
            fault==8?(op>=25&&dst[i]==0x80000000u):
            fault==9?(op>=25&&dst[i]==0x7fc00000u):
            fault==10?(op>=25&&i>=start&&i<vl&&selected(r->mode,i)):0;
            if(choose){pos=i+1;found=1;if(fault==8)flip=0x80000000u;}}
        if(fault==5||fault==33){pos=0;found=1;flip=0x80000000u;}
        if(fault==6){pos=129;found=1;flip=0x80000000u;}
        if(fault==7){returned=1UL<<40;found=1;}
        if(fault==11){pos=128;found=1;flip=0x80000000u;}
        if(fault==12){pos=65;found=1;flip=0x80000000u;}
        if(fault==13||fault==14){pos=0;found=1;out[fault==13?65:129]^=1;}
        if(found){if(fault!=7)out[pos]^=flip;injected=1;}
    }
    ++calls;return returned;
}
#define OP(N) unsigned long op_##N(const word*x,const word*y,word*d,unsigned long v,unsigned long c,const uint8_t*m,unsigned long s){return emulate(N,x,y,d,v,c,m,s);}
OP(0) OP(1) OP(2) OP(3) OP(4) OP(5) OP(6) OP(7) OP(8) OP(9)
OP(10) OP(11) OP(12) OP(13) OP(14) OP(15) OP(16) OP(17) OP(18) OP(19)
OP(20) OP(21) OP(22) OP(23) OP(24) OP(25) OP(26) OP(27) OP(28) OP(29)
OP(30) OP(31) OP(32) OP(33) OP(34)
int main(int argc,char **argv){
    need(argc==3,"fault plus frozen gold file");fault=(unsigned)strtoul(argv[1],0,10);
    gold=malloc(3112200);need(gold!=0,"host gold allocation");FILE *f=fopen(argv[2],"rb");need(f!=0,"gold file");
    need(fread(gold,1,3112200,f)==3112200 && fgetc(f)==EOF,"exact full gold bytes");fclose(f);
    unsigned char raw[522];memset(raw,0xa7,sizeof(raw));e32m4_initialize_output(raw+1);
    need(raw[0]==0xa7&&raw[521]==0xa7,"unaligned520 exact footprint");
    need(!e32m4_packed_mismatch(raw+1,e32m4_expected_ids[0],e32m4_expected_blocks),"unaligned typed equality");
    for(unsigned i=0;i<520;++i){raw[i+1]^=1;need(e32m4_packed_mismatch(raw+1,e32m4_expected_ids[0],e32m4_expected_blocks),"every byte compared, errors still read full");raw[i+1]^=1;}
    long page=sysconf(_SC_PAGESIZE);need(page>520,"page size");
    unsigned char *p=mmap(0,2*(size_t)page,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    need(p!=MAP_FAILED&&!mprotect(p+page,(size_t)page,PROT_NONE),"real PROT_NONE page");
    e32m4_initialize_output(p+page-520);need(!e32m4_packed_mismatch(p+page-520,e32m4_expected_ids[0],e32m4_expected_blocks),"no tail roundup into PROT_NONE");munmap(p,2*(size_t)page);
    memset(mask,0xa5,128);memset(shadow_mask,0xa5,128);running=1;
    int rc=arithmetic_main();
    need(calls==5985&&checks==5985&&elements==766080&&fp_calls==1890,"complete5985 original scope");
    need(total_fp==483840&&total_sb==154350&&total_clear==35280,"all fresh events");
#ifdef PACKED_CASE
    need(full_reads==389025&&full_gold==124041&&full_ids==53865,"full actual/gold/ID counts including errors");
    need(full_hits==33123&&full_misses==14757,"all exact cache hit/miss paths");
#endif
    need(fault<15,"structural mutation must not escape");
    need(fault?(injected&&rc==1&&errors==(fault==13?2u:1u)):(rc==0&&!errors),"original fallback exact failure count");
    printf("HOST_FULL5985 results=766080 guards=11970 fp_calls=1890 fp_stores=483840 mask_SB=154350 calls=%u injected=%u errors=%lu rc=%d\n",calls,injected,(unsigned long)errors,rc);
    free(gold);return rc;
}
