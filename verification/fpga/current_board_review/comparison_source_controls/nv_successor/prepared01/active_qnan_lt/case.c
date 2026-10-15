/* New directed NV-window controls, not archived original programs. */
#include <stdint.h>
#ifdef HOST_CHECK
#include <stdio.h>
#endif
#define N 64
#define ONE 0x3c00
#define TWO 0x4000
#define TRUTH UINT64_C(0x9e35c692396d58b3)
#define GUARD UINT64_C(0x917ac035de6284bf)
struct words { uint64_t lo; uint16_t data[N]; uint64_t hi; };
struct bytes { uint64_t lo; uint8_t data[128]; uint64_t hi; };
struct errors { unsigned data, setup, csr, flags; };
static struct words a,b,seen_a,seen_b;
static struct bytes output,predicate,seen_predicate;
static uint64_t status[12];
extern void replay_text(const char *);
extern void compare(const void *,const void *,void *,const void *,unsigned long,void *);
extern void capture_vectors(void *,void *,void *);
extern void capture_predicate(void *);
static unsigned base(unsigned i) { return (TRUTH>>i)&1; }
static unsigned oldbyte(unsigned i) { return (0xa5U ^ (37U*i))&255; }
static unsigned bit(const uint8_t *p,unsigned i) { return (p[i/8]>>(i%8))&1; }
/* Literal finite truth plus a single explicit ISA NaN override. No DUT inputs. */
static unsigned golden(unsigned i) {
    if(i==NAN_INDEX) return OP==1; /* NE is true for unordered, others false. */
    return (OP==1 || OP==2) ? !base(i) : base(i);
}
static void initialize(void) {
    a.lo=a.hi=b.lo=b.hi=seen_a.lo=seen_a.hi=seen_b.lo=seen_b.hi=GUARD;
    output.lo=output.hi=predicate.lo=predicate.hi=seen_predicate.lo=seen_predicate.hi=GUARD;
    for(unsigned i=0;i<N;++i) {
        if(OP==3) { a.data[i]=base(i)?ONE:TWO; b.data[i]=ONE; }
        else if(OP==2) { a.data[i]=ONE; b.data[i]=base(i)?ONE:TWO; }
        else {
            a.data[i]=(UINT64_C(0x61a7d4398be20c5f)>>i)&1 ? ONE:TWO;
            b.data[i]=base(i)?a.data[i]:(a.data[i]==ONE?TWO:ONE);
        }
        seen_a.data[i]=seen_b.data[i]=0;
    }
    if(NAN_SIDE) b.data[NAN_INDEX]=NAN_BITS;
    else a.data[NAN_INDEX]=NAN_BITS;
    for(unsigned i=0;i<128;++i) {
        output.data[i]=oldbyte(i);
        predicate.data[i]=(0x93U ^ (53U*i))&255;
        seen_predicate.data[i]=0;
    }
    predicate.data[2]=0xad; predicate.data[3]=0xd6;
    for(unsigned i=0;i<12;++i) status[i]=UINT64_MAX;
}
static struct errors check(void) {
    struct errors e={0,0,0,0};
    for(unsigned i=0;i<1024;++i) {
        unsigned old=(oldbyte(i/8)>>(i%8))&1, got=bit(output.data,i);
        if(i<16 || (i<32 && !bit(predicate.data,i))) e.data+=got!=old;
        else if(i<32) e.data+=got!=golden(i);
        else e.data+=got!=old && got!=1 && (i>=N || got!=golden(i));
    }
    for(unsigned i=0;i<N;++i) {
        e.setup+=seen_a.data[i]!=a.data[i]; e.setup+=seen_b.data[i]!=b.data[i];
    }
    for(unsigned i=0;i<128;++i) e.setup+=seen_predicate.data[i]!=predicate.data[i];
    for(unsigned k=0;k<2;++k) {
        e.csr+=status[k*6]!=32; e.csr+=status[k*6+1]!=8;
        e.csr+=status[k*6+2]!=(k?0:16);
        e.flags+=status[k*6+3]!=(k?EXPECTED_FLAGS:1);
        e.csr+=status[k*6+4]!=1; e.csr+=status[k*6+5]!=5;
    }
    e.setup+=a.lo!=GUARD || a.hi!=GUARD || b.lo!=GUARD || b.hi!=GUARD;
    e.setup+=seen_a.lo!=GUARD || seen_a.hi!=GUARD || seen_b.lo!=GUARD || seen_b.hi!=GUARD;
    e.setup+=output.lo!=GUARD || output.hi!=GUARD || predicate.lo!=GUARD || predicate.hi!=GUARD;
    e.setup+=seen_predicate.lo!=GUARD || seen_predicate.hi!=GUARD;
    return e;
}
static unsigned total(struct errors e) { return e.data+e.setup+e.csr+e.flags; }

#ifdef HOST_CHECK
static void putbit(unsigned i,unsigned v) {
    output.data[i/8]=(output.data[i/8]&~(1U<<(i%8)))|(v<<(i%8));
}
static unsigned isnan16(unsigned x) { return (x&0x7c00)==0x7c00 && (x&0x3ff); }
static unsigned scalar_result(unsigned x,unsigned y) {
    if(isnan16(x)||isnan16(y)) return OP==1;
    if(OP==0) return x==y;
    if(OP==1) return x!=y;
    if(OP==2) return x<y; /* Remaining inputs are positive finite ONE/TWO. */
    return x<=y;
}
static unsigned scalar_nv(unsigned x,unsigned y) {
    unsigned xn=isnan16(x),yn=isnan16(y);
    return OP>=2 ? xn||yn : (xn && !(x&0x200)) || (yn && !(y&0x200));
}
static void model(void) {
    unsigned flags=1;
    for(unsigned i=0;i<N;++i) {
        seen_a.data[i]=a.data[i]; seen_b.data[i]=b.data[i];
        if(i>=16 && i<32 && bit(predicate.data,i)) {
            putbit(i,scalar_result(a.data[i],b.data[i]));
            if(scalar_nv(a.data[i],b.data[i])) flags|=16;
        }
    }
    for(unsigned i=0;i<128;++i) seen_predicate.data[i]=predicate.data[i];
    for(unsigned k=0;k<2;++k) {
        status[k*6]=32; status[k*6+1]=8; status[k*6+2]=k?0:16;
        status[k*6+3]=k?flags:1; status[k*6+4]=1; status[k*6+5]=5;
    }
}
int main(void) {
    unsigned tests=0, discriminating=0;
    initialize(); model();
    if(total(check())) return 1;
    ++tests;
    for(unsigned i=0;i<N;++i) if(scalar_result(a.data[i],b.data[i])!=golden(i)) return 2;
    ++tests;
    for(unsigned i=0;i<32;++i) {
        output.data[i/8]^=1U<<(i%8);
        if(!total(check())) return 3;
        output.data[i/8]^=1U<<(i%8); ++tests;
    }
    for(unsigned i=0;i<12;++i) {
        status[i]^=1; if(!total(check())) return 4; status[i]^=1; ++tests;
    }
    for(unsigned i=0;i<5;++i) {
        status[9]^=1U<<i; if(!check().flags) return 5; status[9]^=1U<<i; ++tests;
    }
    seen_a.data[21]^=1; if(!check().setup) return 6; seen_a.data[21]^=1; ++tests;
    seen_b.data[21]^=1; if(!check().setup) return 7; seen_b.data[21]^=1; ++tests;
    seen_predicate.data[127]^=1; if(!check().setup) return 8; seen_predicate.data[127]^=1; ++tests;
    output.hi^=1; if(!check().setup) return 9; output.hi^=1; ++tests;
    for(unsigned i=32;i<1024;++i) putbit(i,1);
    if(total(check())) return 10;
    ++tests;
    putbit(1021,0); if(!check().data) return 11; ++tests;
    initialize(); model();
    for(unsigned i=16;i<32;++i) if(bit(predicate.data,i)) {
        unsigned shifted=scalar_result(a.data[i+16],b.data[i+16]);
        discriminating+=shifted!=golden(i); putbit(i,shifted);
    }
    if(discriminating<9 || !check().data) return 12;
    ++tests;
    printf("HOST_NV_PASS %s checks=%u shifted16_wrong_bits=%u flags=%u\n",CASE_NAME,tests,discriminating,EXPECTED_FLAGS);
    return 0;
}
#else
static void number(unsigned x) {
    char s[16]; unsigned n=15; s[n]=0;
    do { s[--n]='0'+x%10; x/=10; } while(x);
    replay_text(s+n);
}
int SOURCE_MAIN(void) {
    initialize();
    compare(a.data,b.data,output.data,predicate.data,16,status);
    capture_vectors(seen_a.data,seen_b.data,seen_predicate.data);
    capture_predicate(seen_predicate.data);
    struct errors e=check();
    replay_text(total(e)?"FP_NV_FAIL ":"FP_NV_PASS "); replay_text(CASE_NAME);
    replay_text(" cases=1 errors="); number(total(e));
    replay_text(" data="); number(e.data); replay_text(" setup="); number(e.setup);
    replay_text(" csr="); number(e.csr); replay_text(" flag_errors="); number(e.flags);
    replay_text(" expected_flags="); number(EXPECTED_FLAGS);
    replay_text(" actual_flags="); number(status[9]);
    replay_text(" start_after="); number(status[8]); replay_text("\n");
    return total(e)!=0;
}
#endif
