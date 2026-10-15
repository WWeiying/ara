#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(c) do { if(!(c)) { fprintf(stderr,"HOST_REJECT %d %s\n",__LINE__,#c); exit(90); } } while(0)
#if ORIGINAL_RUN
#include "original_case.c"
#else
static void host_store(void *,unsigned,uint64_t);
static uint64_t host_load(const void *,unsigned);
#include "case.c"
#endif
static unsigned calls;
#if !ORIGINAL_RUN
static unsigned output_stores, mask_stores, seed_stores, loads;
#endif
static unsigned long byte_negatives;
static const char *mode;
static char transcript[32768];
static unsigned used;
static int is(const char *s) { return !strcmp(mode,s); }

#if !ORIGINAL_RUN
static void host_store(void *p,unsigned offset,uint64_t value) {
    CHECK(offset%8==0);
    if(p==seed) {
        CHECK(offset<128 && offset==seed_stores*8);
        if(is("drop_seed") && offset==120) return;
        ++seed_stores;
    } else if(p==mask) {
        CHECK(offset<64 && offset==mask_stores*8);
        if(is("drop_mask") && calls==2 && offset==56) return;
        ++mask_stores;
    } else {
        CHECK(p==output && offset<144 && offset==output_stores*8);
        if(is("drop_output") && calls==1 && offset==136) return;
        ++output_stores;
    }
    memcpy((uint8_t *)p+offset,&value,8);
}
static uint64_t host_load(const void *p,unsigned offset) {
    uint64_t value;
    CHECK(p==output && offset<144 && offset%8==0);
    CHECK(offset==loads*8);
    if(is("drop_read") && calls==1 && offset==136) return 0;
    ++loads;
    memcpy(&value,(const uint8_t *)p+offset,8);
    return value;
}
#endif

long replay_write(long n,long fd,long pointer,long length) {
    CHECK(n==64 && fd==1 && length>=0 && used+(unsigned long)length<sizeof(transcript));
    memcpy(transcript+used,(const void *)pointer,(size_t)length);
    used+=(unsigned)length; transcript[used]=0; return length;
}
unsigned long capacity(void) {return 16;}

static unsigned long operate(unsigned op,const void *a,const void *b,void *out,
                             unsigned long vl,unsigned long cap,const void *m,
                             unsigned long rm,unsigned long sticky) {
    unsigned n=calls, want_sticky=n%2; n/=2;
    unsigned want_op=n%3; n/=3;
    unsigned want_rm=n%5; n/=5;
    unsigned maskmode=n%4; n/=4;
    unsigned li=n%7,scenario=n/7;
    const unsigned lengths[]={0,1,2,3,8,15,16};
    CHECK(scenario<8 && op==want_op && rm==want_rm && sticky==want_sticky);
    CHECK(cap==16 && vl==lengths[li] && a==input && b==seed && out==output+8 && m==mask);
    CHECK(sizeof(input)==1024 && sizeof(seed)==128 && sizeof(output)==144 && sizeof(mask)==64);
#if !ORIGINAL_RUN
    if(calls) CHECK(loads == 18);
    loads=0;
    CHECK(output_stores == 18); output_stores=0;
    if(calls%840==0) { CHECK(seed_stores == 16); seed_stores=0; }
    else CHECK(seed_stores==0);
    if(!sticky) { CHECK(mask_stores == 8); mask_stores=0; }
    else CHECK(mask_stores==0);
#endif
    for(unsigned i=0;i<16;++i) CHECK(input[i]==(word)reduction_input(scenario,i,16));
    for(unsigned i=16;i<512;++i) CHECK(input[i]==0);
    for(unsigned i=0;i<64;++i) CHECK(seed[i]==(word)reduction_seed(scenario));
    const unsigned masks[]={255,0,0x55,0x24};
    for(unsigned i=0;i<64;++i) CHECK(mask[i]==masks[maskmode]);
    for(unsigned i=0;i<144;++i) CHECK(output[i]==0x5b);
    unsigned index=scenario*420+((li*4+maskmode)*5+rm)*3+op;
    struct fixture wanted=fixtures[1][index];
    if(vl) { output[8]=(uint8_t)wanted.bits; output[9]=(uint8_t)(wanted.bits>>8); }
    unsigned long status=(unsigned long)(wanted.flags|sticky)<<32;
#if !ORIGINAL_RUN
    CHECK(!packed_mismatch(output,wanted.bits,(unsigned)vl) && loads==18); loads=0;
    /* Independent byte oracle: one wrong byte always contributes exactly one,
       including result bytes, every preserved destination byte and guards. */
    if(is("positive")) for(unsigned byte=0;byte<144;++byte) {
        output[byte]^=1;
        CHECK(packed_mismatch(output,wanted.bits,(unsigned)vl) && loads==18); loads=0;
        unsigned errors=0;
        for(unsigned i=0;i<144;++i) {
            uint8_t expected=vl && i>=8 && i<10 ? wanted.bits>>((i-8)*8):0x5b;
            errors+=output[i]!=expected;
        }
        CHECK(errors==1); ++byte_negatives;
        output[byte]^=1;
    }
#endif
    if(is("each_byte")) output[calls%144]^=1;
    if(is("status")) status|=1;
    if(is("flags")) status^=UINT64_C(16)<<32;
    if(is("mixed") || (is("boundary") && calls<6)) {
        output[0]^=1; output[9]^=1; output[143]^=1;
        status^=UINT64_C(16)<<32; status|=1;
    }
    if(is("VL0") && !vl) output[8]^=1;
    if(is("wrong_bank") && index==1545) {
        output[8]=(uint8_t)fixtures[0][index].bits;
        output[9]=(uint8_t)(fixtures[0][index].bits>>8);
        status=(unsigned long)(fixtures[0][index].flags|sticky)<<32;
    }
    if(is("wrong_nan") && index==1545) output[8]^=1;
    ++calls;
    return status;
}
#define OP(k) unsigned long op_##k(const void*a,const void*b,void*c,unsigned long d,unsigned long e,const void*f,unsigned long g,unsigned long h) {return operate(k,a,b,c,d,e,f,g,h);}
OP(0) OP(1) OP(2)
int main(int argc,char **argv) {
    CHECK(argc==2); mode=argv[1];
    uint64_t endian=1; CHECK(*(uint8_t*)&endian==1);
    int rc=fp_redspecial_e16_mf4_full6720_main();
    CHECK(calls==6720);
#if !ORIGINAL_RUN
    CHECK(loads == 18);
    CHECK(byte_negatives==(is("positive")?967680UL:0UL) && !seed_stores && !mask_stores && !output_stores);
#endif
    CHECK(!is("drop_output") && !is("drop_mask") && !is("drop_seed") && !is("drop_read"));
    CHECK(rc==(is("positive")?0:1));
    if(is("positive")) CHECK(strstr(transcript,"cases=6720 flags_seen=21 errors=0\n"));
    if(is("boundary")) {
        unsigned details=0;
        for(char *s=transcript;(s=strstr(s,"RVV_FP_REDSPECIAL_DETAIL "));++s)++details;
        CHECK(details==4 && strstr(transcript,"errors=24\n"));
    }
    fputs(transcript,stdout);
    fprintf(stderr,"HOST_PASS original=%d mode=%s calls=%u mutations=%lu\n",ORIGINAL_RUN,mode,calls,byte_negatives);
    return 0;
}
