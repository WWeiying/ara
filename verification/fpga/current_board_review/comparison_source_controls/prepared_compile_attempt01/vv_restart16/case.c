/* New finite-value discriminator, not an archived original-source replay. */
#include <stdint.h>
#ifdef HOST_CHECK
#include <stdio.h>
#endif
#define N 64
#define GUARD UINT64_C(0x917ac035de6284bf)
#define TRUTH UINT64_C(0x9e35c692396d58b3)
#define ONE 0x3c00
#define TWO 0x4000
struct words { uint64_t lo; uint16_t data[N]; uint64_t hi; };
struct bytes { uint64_t lo; uint8_t data[128]; uint64_t hi; };
static struct words a, b, seen_a, seen_b;
static struct bytes output, predicate, seen_predicate;
static uint64_t status[12];
static unsigned start, scalar;
extern void replay_text(const char *);
extern void compare(const void *, const void *, void *, const void *, unsigned long, void *);
extern void capture_vectors(void *, void *, void *);
extern void capture_predicate(void *);

static unsigned truth(unsigned i) { return (TRUTH >> i) & 1; }
static unsigned bit(const uint8_t *p, unsigned i) { return (p[i/8] >> (i%8)) & 1; }
#ifdef HOST_CHECK
static void putbit(uint8_t *p, unsigned i, unsigned v) {
    p[i/8] = (p[i/8] & ~(1U << (i%8))) | (v << (i%8));
}
#endif
static unsigned oldbyte(unsigned i) { return (0xa5U ^ (37U*i)) & 255; }
static void initialize(void) {
    a.lo=b.lo=seen_a.lo=seen_b.lo=output.lo=predicate.lo=seen_predicate.lo=GUARD;
    a.hi=b.hi=seen_a.hi=seen_b.hi=output.hi=predicate.hi=seen_predicate.hi=GUARD;
    for(unsigned i=0;i<N;++i) {
        a.data[i] = scalar ? (truth(i) ? ONE : TWO) :
                    ((UINT64_C(0x61a7d4398be20c5f) >> i)&1 ? ONE : TWO);
        b.data[i] = truth(i) ? a.data[i] : (a.data[i]==ONE ? TWO : ONE);
        seen_a.data[i]=seen_b.data[i]=0;
    }
    for(unsigned i=0;i<128;++i) {
        output.data[i]=oldbyte(i);
        predicate.data[i]=(0x93U ^ (i*53U)) & 255;
        seen_predicate.data[i]=0;
    }
    predicate.data[2]=0xad;
    predicate.data[3]=0xd6;
    for(unsigned i=0;i<12;++i) status[i]=UINT64_MAX;
}

/* Golden truth is literal and independent of observed vector data/results. */
static unsigned check(void) {
    unsigned errors=0;
    for(unsigned i=0;i<1024;++i) {
        unsigned old=(oldbyte(i/8)>>(i%8))&1;
        unsigned got=bit(output.data,i);
        if(i<start || (i<32 && !bit(predicate.data,i))) errors+=got!=old;
        else if(i<32) errors+=got!=truth(i);
        else errors+=got!=old && got!=1 && (i>=N || got!=truth(i));
    }
    for(unsigned i=0;i<N;++i) {
        errors+=seen_a.data[i]!=a.data[i];
        errors+=seen_b.data[i]!=b.data[i];
        /* Independently validate the generator, including unused tail inputs. */
        errors+=(scalar ? a.data[i]==ONE : a.data[i]==b.data[i]) != truth(i);
    }
    for(unsigned i=0;i<128;++i) errors+=seen_predicate.data[i]!=predicate.data[i];
    for(unsigned k=0;k<2;++k) {
        errors+=status[k*6]!=32;
        errors+=status[k*6+1]!=8; /* e16,m1,tu,mu */
        errors+=status[k*6+2]!=(k ? 0 : start);
        errors+=status[k*6+3]!=1; /* Preserve NX, introduce no flags. */
        errors+=status[k*6+4]!=1; /* frm=RTZ */
        errors+=status[k*6+5]!=5; /* vxrm=2,vxsat=1 */
    }
    errors+=a.lo!=GUARD || a.hi!=GUARD || b.lo!=GUARD || b.hi!=GUARD;
    errors+=seen_a.lo!=GUARD || seen_a.hi!=GUARD || seen_b.lo!=GUARD || seen_b.hi!=GUARD;
    errors+=output.lo!=GUARD || output.hi!=GUARD || predicate.lo!=GUARD || predicate.hi!=GUARD;
    errors+=seen_predicate.lo!=GUARD || seen_predicate.hi!=GUARD;
    return errors;
}

#ifdef HOST_CHECK
static void model(void) {
    for(unsigned i=0;i<N;++i) { seen_a.data[i]=a.data[i]; seen_b.data[i]=b.data[i]; }
    for(unsigned i=0;i<128;++i) seen_predicate.data[i]=predicate.data[i];
    for(unsigned i=start;i<32;++i) if(bit(predicate.data,i)) putbit(output.data,i,truth(i));
    for(unsigned k=0;k<2;++k) {
        status[k*6]=32; status[k*6+1]=8; status[k*6+2]=k ? 0 : start;
        status[k*6+3]=1; status[k*6+4]=1; status[k*6+5]=5;
    }
}
int main(void) {
    unsigned tests=0;
    for(unsigned c=0;c<3;++c) {
        start=c==1 ? 0 : 16; scalar=c==2;
        initialize(); model(); if(check()) return 1; ++tests;
        for(unsigned i=16;i<32;++i) if(truth(i)==truth(i+16)) return 2;
        /* Every result bit before VL is checked, including prefix/masked-off. */
        for(unsigned i=0;i<32;++i) {
            output.data[i/8]^=1U<<(i%8);
            if(!check()) return 3;
            output.data[i/8]^=1U<<(i%8); ++tests;
        }
        for(unsigned i=0;i<12;++i) { status[i]^=1; if(!check()) return 4; status[i]^=1; ++tests; }
        seen_a.data[20]^=1; if(!check()) return 5; seen_a.data[20]^=1; ++tests;
        seen_b.data[20]^=1; if(!check()) return 6; seen_b.data[20]^=1; ++tests;
        seen_predicate.data[127]^=1; if(!check()) return 7; seen_predicate.data[127]^=1; ++tests;
        output.hi^=1; if(!check()) return 8; output.hi^=1; ++tests;
        /* Tail admits only ISA alternatives, never a blanket don't-care. */
        for(unsigned i=32;i<1024;++i) putbit(output.data,i,1);
        if(check()) return 9;
        ++tests;
        unsigned tail=1021;
        if(!((oldbyte(tail/8)>>(tail%8))&1)) return 10;
        putbit(output.data,tail,0); if(!check()) return 11; ++tests;
        initialize(); model();
        for(unsigned i=start;i<32;++i) if(bit(predicate.data,i)) putbit(output.data,i,truth(i+16));
        if(!check()) return 12; ++tests;
    }
    printf("HOST_CHECK_PASS checks=%u cases=3 shifted16_rejected=3\n",tests);
    return 0;
}
#else
static void number(unsigned x) {
    char s[16]; unsigned n=15; s[n]=0;
    do { s[--n]='0'+x%10; x/=10; } while(x);
    replay_text(s+n);
}
int SOURCE_MAIN(void) {
    start=START; scalar=SCALAR;
    initialize();
    compare(a.data,b.data,output.data,predicate.data,start,status);
    capture_vectors(seen_a.data,seen_b.data,seen_predicate.data);
    capture_predicate(seen_predicate.data);
    unsigned errors=check();
    replay_text(errors ? "FP_SOURCE_FAIL " : "FP_SOURCE_PASS ");
    replay_text(CASE_NAME); replay_text(" cases=1 errors="); number(errors);
    replay_text(" flags="); number(status[9]); replay_text(" start_after="); number(status[8]);
    replay_text("\n");
    return errors!=0;
}
#endif
