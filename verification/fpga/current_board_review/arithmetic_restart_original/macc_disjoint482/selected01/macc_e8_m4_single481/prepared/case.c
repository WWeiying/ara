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
#ifndef INPUT_SEEDS
#define INPUT_SEEDS 3
#endif
#ifndef UNMASKED_SUITE
#define UNMASKED_SUITE 0
#endif
#ifndef CARRY_INPUT_SUITE
#define CARRY_INPUT_SUITE 0
#endif
#ifndef ACCUMULATOR_TRIALS
#define ACCUMULATOR_TRIALS 1
#endif

static word initial_destination(unsigned trial, unsigned i) {
#ifdef MACC_ACCUMULATORS
    switch(trial) {
    case 0:return 0;
    case 1:return (word)-1;
    case 2:return (word)(UINT64_C(1)<<(SEW-1));
    case 3:return i&1 ? (word)UINT64_C(0xaaaaaaaaaaaaaaaa):
                       (word)UINT64_C(0x5555555555555555);
    default:return (word)(UINT64_C(0x937ad68de41c725f)+
                          UINT64_C(0x9e3779b97f4a7c15)*i);
    }
#else
    (void)trial;(void)i;return (word)0x5b;
#endif
}

static word a[1024], b[1024], out[1026];
static uint8_t mask[128];
static uint64_t checks, elements, errors;
static unsigned accumulator_trial;
extern unsigned long capacity(void);
typedef unsigned long (*operation)(const word *, const word *, word *,
                                  unsigned long, unsigned long,
                                  const uint8_t *, unsigned long, unsigned long);
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
#if !defined(INTEGER_MACC_SUITE) && !defined(INTEGER_CARRY_SUITE)
static int64_t signed_word(uint64_t x) {
    uint64_t sign=UINT64_C(1)<<(SEW-1);
    return (int64_t)((x^sign)-sign);
}
#endif
#if !INTEGER_EXTENSION
#if !defined(INTEGER_MACC_SUITE) && !defined(INTEGER_CARRY_SUITE)
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
#endif
#ifdef INTEGER_SCALAR_SUITE
static word scalar_value(unsigned op, word x, word vector_y, unsigned carry, word old_destination) {
#ifndef INTEGER_MACC_SUITE
    (void)old_destination;
#endif
#ifdef INTEGER_CARRY_SUITE
    uint64_t y=op==0 || op==4 ? vector_y : op==2 ? (word)-16 : op==3 ? (word)15:b[0];
    return op<4 ? (uint64_t)x+y+carry:(uint64_t)x-y-carry;
#else
    (void)carry;
#ifdef INTEGER_MACC_SUITE
#if MACC_ALIAS_FIRST
    x=old_destination;
#endif
#if MACC_ALIAS_SECOND
    vector_y=old_destination;
#endif
    uint64_t y=op<4 ? vector_y:b[0];
    uint64_t old=old_destination;
    switch(op%4) {
    case 0:return old+(uint64_t)x*y;
    case 1:return old-(uint64_t)x*y;
    case 2:return op<4 ? old*(uint64_t)x+y:old*y+(uint64_t)x;
    default:return op<4 ? y-old*(uint64_t)x:(uint64_t)x-old*y;
    }
#else
    (void)vector_y;
#ifdef INTEGER_IMMEDIATE_SUITE
    static const unsigned mapping[]={IMMEDIATE_ORACLE};
    static const int constants[]={IMMEDIATE_VALUES};
    word y=(word)constants[op];
    op=mapping[op];
#else
    word y=b[0];
#endif
    if(op<17)return value(op,x,y);
    if(op==17)return y-x;
    if(op==18)return ((unsigned __int128)x*y)>>SEW;
    __int128 sx=signed_word(x),sy=signed_word(y);
    return op==19 ? (sx*sy)>>SEW : (sx*(__int128)(uint64_t)y)>>SEW;
#endif
#endif
}
#endif
#endif
static unsigned selected(unsigned mode,unsigned i) {
    return mode==0 || (mode==1 ? (i&1) : mode==2 && (i%7==2));
}
#if INTEGER_EXTENSION
static __int128 rounded(__int128 x, unsigned shift, unsigned rm) {
    if(!shift)return x;
    unsigned __int128 bits=(unsigned __int128)x;
    unsigned __int128 low=((unsigned __int128)1<<shift)-1;
    unsigned half=(bits>>(shift-1))&1;
    unsigned odd=(bits>>shift)&1;
    unsigned increment=rm==0 ? half : rm==1 ? half && ((bits&(low>>1)) || odd) :
                       rm==2 ? 0 : !odd && (bits&low);
    return (x>>shift)+increment;
}
static word extra_value(unsigned op, word x, word y, unsigned rm, unsigned *sat) {
#ifdef FIXED_SCALAR_SUITE
    static const unsigned mapping[]={SCALAR_ORACLE};
    static const unsigned immediate[]={SCALAR_IMMEDIATE};
    static const int constants[]={SCALAR_IMMEDIATE_VALUES};
    y=immediate[op] ? (word)constants[op]:b[0];
    op=mapping[op];
#endif
    __int128 sx=signed_word(x),sy=signed_word(y),z;
    __int128 lo=-((__int128)1<<(SEW-1)),hi=-lo-1;
    unsigned __int128 umax=(word)-1;
#ifdef FRACTIONAL_SUITE
    rm&=3;
    if(op==
#ifdef FIXED_SCALAR_SUITE
       20
#else
       0
#endif
       ){
        z=rounded(sx*sy,SEW-1,rm);
        if(z>hi){*sat=1;return hi;}
        return z;
    }
#ifndef FIXED_SCALAR_SUITE
    op=op==1 ? 4:op==2 ? 3:6;
#endif
#endif
    switch(op) {
    case 0:return ((unsigned __int128)x*y)>>SEW;
    case 1:return (sx*sy)>>SEW;
    case 2:return (sx*(__int128)(uint64_t)y)>>SEW;
    case 3:z=(unsigned __int128)x+y;if((unsigned __int128)z>umax){*sat=1;return (word)-1;}return z;
    case 4:z=sx+sy;break;
    case 5:if(x<y){*sat=1;return 0;}return x-y;
    case 6:z=sx-sy;break;
    case 7:return rounded((__int128)(uint64_t)x+y,1,rm);
    case 8:return rounded(sx+sy,1,rm);
    case 9:return rounded((__int128)(uint64_t)x-y,1,rm);
    case 10:return rounded(sx-sy,1,rm);
    case 11:return rounded((__int128)(uint64_t)x,y&(SEW-1),rm);
    case 12:return rounded(sx,y&(SEW-1),rm);
    case 13:return x&y;
    case 14:return x|y;
    case 15:return x^y;
    case 16:return x<y ? x:y;
    case 17:return x>y ? x:y;
    case 18:return sx<sy ? x:y;
    case 19:return sx>sy ? x:y;
    default:return 0;
    }
    if(z<lo){*sat=1;return lo;}
    if(z>hi){*sat=1;return hi;}
    return z;
}
#endif
static void failure(unsigned op,unsigned seed,unsigned vl,unsigned mode,
                    unsigned start,unsigned i,uint64_t expected,uint64_t actual) {
    if(++errors>20)return;
    text("RVV_MATRIX_FAIL op=");text(names[op]);
    text(" sew=");number(SEW);text(" seed=");number(seed);
#ifdef MACC_ACCUMULATORS
    text(" accumulator=");number(accumulator_trial);
#endif
    text(" vl=");number(vl);text(" mask=");number(mode);
    text(" vstart=");number(start);text(" element=");number(i);
    text(" expected=");number(expected);text(" actual=");number(actual);
    text("\n");
}
int macc_main(void) {
    unsigned source_trial=0;
    unsigned cap=capacity();
    if(!cap || cap>1024){text("RVV_MATRIX_UNSUPPORTED_CAPACITY\n");return 2;}
#ifdef RESTART_SUITE
    unsigned long max_start;
    __asm__ volatile("csrr %0,vlenb":"=r"(max_start));
    max_start=max_start*8-1;
#endif
    unsigned lengths[]={0,1,2,3,cap/2,cap-1,cap};
    for(unsigned seed=0;seed<INPUT_SEEDS;++seed) {
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
#ifdef FIXED_SCALAR_SUITE
        b[0]=seed==0 ? (word)7:seed==1 ? (word)(UINT64_C(1)<<(SEW-1)):
                                                   (word)((UINT64_C(1)<<(SEW-1))-1);
#endif
#ifdef INTEGER_SCALAR_SUITE
        static const word scalars[]={0,7,(word)-1,
            (word)(UINT64_C(1)<<(SEW-1)),(word)((UINT64_C(1)<<(SEW-1))-1)};
        b[0]=scalars[seed];
#endif
        for(unsigned op=0;op<OPERATION_COUNT;++op)
        for(unsigned li=0;li<7;++li) {
            unsigned vl=lengths[li];if(vl>cap)continue;
            for(unsigned accumulator=0;accumulator<ACCUMULATOR_TRIALS;++accumulator)
            for(unsigned mode=0;mode<
#if defined(FRACTIONAL_SUITE) || defined(INTEGER_SCALAR_SUITE)
                4
#else
                3
#endif
                ;++mode) {
                for(unsigned i=0;i<128;++i)mask[i]=0;
                for(unsigned i=0;i<cap;++i)
                    if(selected(mode,i))mask[i/8]|=1u<<(i%8);
                unsigned trials=
#ifdef RESTART_SUITE
                    4;
#else
                    kinds[op]==0 ? 3:1;
#endif
                for(unsigned si=0;si<trials;++si)
                for(unsigned rm=0;rm<
#ifdef FRACTIONAL_SUITE
                    8u
#else
                    (INTEGER_EXTENSION ? 4u:1u)
#endif
                    ;++rm) {
                    unsigned start=
#ifdef RESTART_SUITE
                        si==0 ? 1:si==1 ? vl/2:si==2 ? (vl<=max_start ? vl:cap-1):cap-1;
#else
                        si==0 ? 0:si==1 ? vl/2:(vl<cap ? vl:cap-1);
#endif
                    unsigned original_trial=source_trial++;
                    if(original_trial<481 || original_trial>481) continue;
                    text("MACC_ORIGINAL_TRIAL index=");number(original_trial);text("\n");
                    accumulator_trial=accumulator;
                    word sentinel=(word)0x5b;
#if SEW >= 32 && !INTEGER_EXTENSION && !defined(INTEGER_SCALAR_SUITE)
                    if(op>=25)
                        for(unsigned i=0;i<cap;++i) {
                            a[i]=fp_inputs[(i+seed)%8];
                            b[i]=fp_inputs[(i*3+seed)%8];
                        }
#endif
                    for(unsigned i=0;i<cap+2;++i)out[i]=sentinel;
                    for(unsigned i=0;i<cap;++i)
                        out[i+1]=initial_destination(accumulator,i);
#if defined(TRACE_OP0) || defined(TRACE_RESTART_BOUNDARIES)
#ifdef TRACE_OP0
                    if(op==0) {
#else
                    if(op==0 && seed==0 && mode==0 && rm==0 && accumulator==0) {
#endif
                        text("RVV_TRIAL seed=");number(seed);
                        text(" vl=");number(vl);text(" mask=");number(mode);
                        text(" vstart=");number(start);
                        text(" completed=");number(checks);text("\n");
                        /* Linux tty drain omitted; OS timing is not reproduced. */
                    }
#endif
                    unsigned long vs=functions[op](a,b,out+1,vl,cap,mask,start,rm);
                    if((uint32_t)vs)failure(op,seed,vl,mode,start,cap+2,0,(uint32_t)vs);
                    unsigned packed=0;
                    unsigned saturation=0;
#ifdef FRACTIONAL_SUITE
                    saturation=rm>>2;
#endif
                    word reduced=b[0];
                    if(kinds[op]==2)
                        for(unsigned i=0;i<vl;++i)
                            if(selected(mode,i)) {
#if INTEGER_EXTENSION
                                reduced=extra_value(op,reduced,a[i],rm,&saturation);
#else
                                reduced+=a[i];
#endif
                            }
                    for(unsigned i=0;i<cap;++i) {
                        word expected=initial_destination(accumulator,i);
                        if(kinds[op]==2) {
                            if(i==0 && vl)expected=reduced;
                        } else if(kinds[op]==3) {
                            while(packed<vl && !selected(mode,packed))++packed;
                            if(packed<vl)expected=a[packed++];
                        } else if(i<vl && i>=start && (UNMASKED_SUITE || CARRY_INPUT_SUITE || selected(mode,i))) {
#if defined(INTEGER_SCALAR_SUITE)
#ifdef MACC_CHAIN_STEPS
                            for(unsigned step=0;step<MACC_CHAIN_STEPS;++step) {
                                unsigned chain_op=MACC_CHAIN_MIXED ? (op&~3u)|((op+step)%4):op;
                                expected=scalar_value(chain_op,a[i],b[i],selected(mode,i),expected);
                            }
#else
                            expected=scalar_value(op,a[i],b[i],selected(mode,i),expected);
#endif
#elif INTEGER_EXTENSION
                            expected=extra_value(op,a[i],b[i],rm,&saturation);
#else
                            if(op<19)expected=value(op,a[i],b[i]);
                            else if(op==19) {if(i>=2)expected=a[i-2];}
                            else if(op==20)expected=i+2<cap ? a[i+2]:0;
                            else if(op==21)expected=b[i]<cap ? a[b[i]]:0;
                            else if(op==24)expected=a[i];
#if SEW >= 32
                            else if(op>=25)expected=fp_expected[op-25][((i+seed)%8)*8+(i*3+seed)%8];
#endif
#endif
                        }
                        unsigned inactive=kinds[op]==2 ? (vl && i!=0) :
                                          i>=vl || (i>=start && !UNMASKED_SUITE && !CARRY_INPUT_SUITE && !selected(mode,i));
                        if(out[i+1]!=expected && !(AGNOSTIC_POLICY && vl && inactive && out[i+1]==(word)-1))
                            failure(op,seed,vl,mode,start,i,expected,out[i+1]);
                        ++elements;
                    }
                    if((vs>>32)!=saturation)
                        failure(op,seed,vl,mode,start,cap+3,saturation,vs>>32);
                    if(out[0]!=sentinel || out[cap+1]!=sentinel)
                        failure(op,seed,vl,mode,start,cap+1,sentinel,out[cap+1]);
                    ++checks;
                    if(source_trial==482) goto selection_complete;
                }
            }
        }
    }
selection_complete:
    text(errors ? "RVV_MATRIX_FAILED sew=":"RVV_MATRIX_PASS sew=");number(SEW);text(" vlmax=");number(cap);
    text(" cases=");number(checks);text(" elements=");number(elements);
    text(" errors=");number(errors);
    text(" seeds=");number(INPUT_SEEDS);
    text(" guard_tail_mask_vstart=checked\n");return errors ? 1:0;
}
