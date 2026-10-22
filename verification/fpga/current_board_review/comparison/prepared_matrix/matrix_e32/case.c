/* Independent directed regression, not an original-source replay. */
#include <stdint.h>
#if SEW == 16
typedef uint16_t word;
#define ONE 0x3c00ULL
#define TWO 0x4000ULL
#define SNAN 0x7c55ULL
#define QNAN 0x7e55ULL
#elif SEW == 32
typedef uint32_t word;
#define ONE 0x3f800000ULL
#define TWO 0x40000000ULL
#define SNAN 0x7f800055ULL
#define QNAN 0x7fc00055ULL
#else
typedef uint64_t word;
#define ONE 0x3ff0000000000000ULL
#define TWO 0x4000000000000000ULL
#define SNAN 0x7ff0000000000055ULL
#define QNAN 0x7ff8000000000055ULL
#endif
#define MAX 288
static word a[MAX], b[MAX], seen_a[MAX], seen_b[MAX];
static uint8_t mask[38], out[38], seen_mask[38];
extern unsigned long cmp(unsigned, const void *, const void *, void *, unsigned long,
                         unsigned long, const void *, unsigned long);
extern void inspect(void *, void *, void *);
extern void replay_text(const char *);
static void number(unsigned x) {
    char s[16]; unsigned n=15; s[n]=0;
    do { s[--n]='0'+x%10; x/=10; } while(x);
    replay_text(s+n);
}
static unsigned bit(const uint8_t *p, unsigned i) { return (p[i/8]>>(i%8))&1; }

static unsigned run(unsigned op, unsigned kind, unsigned side, unsigned mode) {
    unsigned slice=256/SEW, count=2*slice+4, vl=count, start=0;
    unsigned idx=5, unmasked=mode==2, sticky=mode>=4;
    if(mode==2) { vl=count-1; idx=count-1; }
    if(mode==3) { vl=8; start=6; }
    if(mode>=4) idx=count-3;
    if(mode>=6) { count=272; vl=269; idx=261; }
    for(unsigned i=0;i<count;++i) { a[i]=ONE; b[i]=(i&1)?TWO:ONE; seen_a[i]=0; seen_b[i]=0; }
    for(unsigned i=0;i<38;++i) { mask[i]=255; out[i]=0x5b; seen_mask[i]=0; }
    if(mode==1) for(unsigned i=0;i<38;++i) mask[i]=0;
    if(mode==5 || mode==7) mask[idx/8]&=~(1U<<(idx%8));
    if(kind) { if(side) b[idx]=kind==1?SNAN:QNAN; else a[idx]=kind==1?SNAN:QNAN; }
    /* op bits select only ISA opcode, vm and sticky; no hints or scalar search. */
    unsigned long status=cmp(op|(unmasked<<2)|(sticky<<3),a,b,out+1,vl,count,mask,start);
    inspect(seen_a,seen_b,seen_mask);
    unsigned expected=sticky, data=0, setup=0;
    for(unsigned i=0;i<count;++i) {
        unsigned nan=kind && i==idx;
        unsigned eq=!nan && a[i]==b[i];
        unsigned lt=!nan && a[i]<b[i]; /* finite inputs are positive 1 or 2 */
        unsigned want=op==0?eq:op==1?!eq:op==2?lt:(lt||eq);
        unsigned active=i>=start && i<vl && (unmasked || bit(mask,i));
        unsigned old=(0x5b>>(i%8))&1, got=bit(out+1,i);
        if(active) { data+=got!=want; if(nan && (kind==1 || op>=2)) expected|=16; }
        else if(i<start || i<vl) data+=got!=old;
        else data+=got!=old && got!=1 && got!=want;
        setup+=seen_a[i]!=a[i] || seen_b[i]!=b[i];
    }
    for(unsigned i=0;i<(count+7)/8;++i) setup+=seen_mask[i]!=mask[i];
    for(unsigned i=0;i<38;++i) if(i==0 || i>(count+7)/8) setup+=out[i]!=0x5b;
    unsigned actual=status>>32, errors=data+setup+(actual!=expected)+((uint32_t)status!=0);
    if(errors) {
        replay_text("MATRIX_DETAIL sew="); number(SEW);
        replay_text(" op="); number(op); replay_text(" kind="); number(kind);
        replay_text(" side="); number(side); replay_text(" mode="); number(mode);
        replay_text(" idx="); number(idx); replay_text(" vl="); number(vl);
        replay_text(" start="); number(start); replay_text(" expected_flags="); number(expected);
        replay_text(" actual_flags="); number(actual); replay_text(" data="); number(data);
        replay_text(" setup="); number(setup); replay_text(" vstart="); number((uint32_t)status);
        replay_text("\n");
    }
    return errors;
}

int MATRIX_MAIN(void) {
    unsigned errors=0, cases=0;
    for(unsigned op=0;op<4;++op) {
        errors+=run(op,0,0,0); ++cases;
        for(unsigned kind=1;kind<=2;++kind)
            for(unsigned side=0;side<2;++side)
                for(unsigned mode=0;mode<6;++mode) { errors+=run(op,kind,side,mode); ++cases; }
    }
#if SEW == 16
    for(unsigned mode=6;mode<8;++mode) { errors+=run(0,1,1,mode); ++cases; }
#endif
    replay_text(errors?"MATRIX_FAIL sew=":"MATRIX_PASS sew="); number(SEW);
    replay_text(" cases="); number(cases); replay_text(" errors="); number(errors); replay_text("\n");
    return errors!=0;
}
