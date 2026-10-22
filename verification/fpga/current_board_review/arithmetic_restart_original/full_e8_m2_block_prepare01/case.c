#include <stdint.h>

#ifndef SEW
#error SEW must be specified
#endif
#if SEW == 8
typedef uint8_t word;
#elif SEW == 16
typedef uint16_t word;
#elif SEW == 32
typedef uint32_t word;
#elif SEW == 64
typedef uint64_t word;
#endif
#include "operations.h"
static word a[1024], b[1024];
static word out[1026] __attribute__((aligned(8)));
#include "dictionary.h"
#include "packed.h"
static uint8_t mask[128];
static uint64_t checks, elements, errors;
extern unsigned long capacity(void);
typedef unsigned long (*operation)(const word *, const word *, word *,
                                  unsigned long, unsigned long,
                                  const uint8_t *, unsigned long);
static operation functions[] = { OPERATION_FUNCTIONS };
static const char *names[] = { OPERATION_NAMES };
static const unsigned kinds[] = { OPERATION_KINDS };

extern long replay_write(long,long,long,long);
#define syscall3 replay_write
static void text(const char *s) {
    long n=0; while(s[n])++n;
    syscall3(64,1,(long)s,n);
}
static void number(uint64_t n) {
    char s[24]; unsigned i=23; s[i]=0;
    do{s[--i]='0'+n%10;n/=10;}while(n);
    text(s+i);
}
static int64_t signed_word(uint64_t x) {
    uint64_t sign=UINT64_C(1)<<(SEW-1);
    return (int64_t)((x^sign)-sign);
}
static word value(unsigned op, word x, word y) {
    switch(op) {
    case 0:return x+y;
    case 1:return x-y;
    case 2:return x&y;
    case 3:return x|y;
    case 4:return x^y;
    case 5:return (uint64_t)x << (y&(SEW-1));
    case 6:return (uint64_t)x >> (y&(SEW-1));
    case 7:return signed_word(x) >> (y&(SEW-1));
    case 8:return x<y ? x:y;
    case 9:return x>y ? x:y;
    case 10:return signed_word(x)<signed_word(y) ? x:y;
    case 11:return signed_word(x)>signed_word(y) ? x:y;
    case 12:return (uint64_t)x*y;
    case 13:return y ? (uint64_t)x/y : (word)-1;
    case 14:return y ? (uint64_t)x%y : x;
    case 15:
    case 16: {
        int64_t sx=signed_word(x), sy=signed_word(y);
        if(!sy)return op==15 ? (word)-1:x;
        if(x==(word)(UINT64_C(1)<<(SEW-1)) && y==(word)-1)
            return op==15 ? x:0;
        return op==15 ? sx/sy:sx%sy;
    }
    case 17:return x+7;
    case 18:return x+3;
    default:return 0;
    }
}
static unsigned selected(unsigned mode,unsigned i) {
    return mode==0 || (mode==1 ? (i&1) : mode==2 && (i%7==2));
}
static void failure(unsigned op,unsigned seed,unsigned vl,unsigned mode,
                    unsigned start,unsigned i,uint64_t expected,uint64_t actual) {
    if(++errors>20)return;
    text("RVV_MATRIX_FAIL op=");text(names[op]);
    text(" sew=");number(SEW);text(" seed=");number(seed);
    text(" vl=");number(vl);text(" mask=");number(mode);
    text(" vstart=");number(start);text(" element=");number(i);
    text(" expected=");number(expected);text(" actual=");number(actual);
    text("\n");
}
int arithmetic_main(void) {
    unsigned cap=capacity();
    if(cap!=256){text("RVV_MATRIX_UNSUPPORTED_CAPACITY\n");return 2;}
    unsigned lengths[]={0,1,2,3,cap/2,cap-1,cap};
    for(unsigned seed=0;seed<3;++seed) {
        uint64_t random=UINT64_C(0x937ad68de41c725f)^seed;
        for(unsigned i=0;i<cap;++i) {
            random^=random<<13;random^=random>>7;random^=random<<17;
            a[i]=random;b[i]=random>>19;
            switch(i%8) {
            case 0:a[i]=0;b[i]=0;break;
            case 1:a[i]=(word)-1;b[i]=1;break;
            case 2:a[i]=(word)(UINT64_C(1)<<(SEW-1));b[i]=(word)-1;break;
            case 3:b[i]=SEW;break;
            }
        }
        for(unsigned op=0;op<OPERATION_COUNT;++op)
        for(unsigned li=0;li<7;++li) {
            unsigned vl=lengths[li];if(vl>cap)continue;
            for(unsigned mode=0;mode<3;++mode) {
                initialize_mask(mask,mode);
                unsigned trials=kinds[op]==0 ? 3:1;
                for(unsigned si=0;si<trials;++si) {
                    unsigned start=si==0 ? 0:si==1 ? vl/2:(vl<cap ? vl:cap-1);
                    word sentinel=(word)0x5b;
#if SEW >= 32
                    if(op>=25)
                        for(unsigned i=0;i<cap;++i) {
                            a[i]=fp_inputs[(i+seed)%8];
                            b[i]=fp_inputs[(i*3+seed)%8];
                        }
#endif
                    initialize_output(out);
#ifdef TRACE_OP0
                    if(op==0) {
                        text("RVV_TRIAL seed=");number(seed);
                        text(" vl=");number(vl);text(" mask=");number(mode);
                        text(" vstart=");number(start);
                        text(" completed=");number(checks);text("\n");
                        /* Optional Linux tty drain absent in bare metal. */
                    }
#endif
                    unsigned long vs=functions[op](a,b,out+1,vl,cap,mask,start);
                    if(vs)failure(op,seed,vl,mode,start,cap+2,0,vs);
                    if(packed_mismatch(out,checks)) {
                    unsigned packed=0;
                    word reduced=b[0];
                    if(kinds[op]==2)
                        for(unsigned i=0;i<vl;++i)
                            if(selected(mode,i))reduced+=a[i];
                    for(unsigned i=0;i<cap;++i) {
                        word expected=sentinel;
                        if(kinds[op]==2) {
                            if(i==0 && vl)expected=reduced;
                        } else if(kinds[op]==3) {
                            while(packed<vl && !selected(mode,packed))++packed;
                            if(packed<vl)expected=a[packed++];
                        } else if(i<vl && i>=start && selected(mode,i)) {
                            if(op<19)expected=value(op,a[i],b[i]);
                            else if(op==19) {if(i>=2)expected=a[i-2];}
                            else if(op==20)expected=i+2<cap ? a[i+2]:0;
                            else if(op==21)expected=b[i]<cap ? a[b[i]]:0;
                            else if(op==24)expected=a[i];
#if SEW >= 32
                            else if(op>=25)expected=fp_expected[op-25][((i+seed)%8)*8+(i*3+seed)%8];
#endif
                        }
                        if(out[i+1]!=expected)
                            failure(op,seed,vl,mode,start,i,expected,out[i+1]);
                        ++elements;
                    }
                    if(out[0]!=sentinel || out[cap+1]!=sentinel)
                        failure(op,seed,vl,mode,start,cap+1,sentinel,out[cap+1]);
                    } else elements+=cap;
                    ++checks;
                }
            }
        }
    }
    text(errors ? "RVV_MATRIX_FAILED sew=":"RVV_MATRIX_PASS sew=");number(SEW);text(" vlmax=");number(cap);
    text(" cases=");number(checks);text(" elements=");number(elements);
    text(" errors=");number(errors);
    text(" seeds=3 guard_tail_mask_vstart=checked\n");return errors ? 1:0;
}
