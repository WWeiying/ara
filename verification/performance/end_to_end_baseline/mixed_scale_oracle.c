#include <fenv.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint32_t rng = 0x39e017abu;
static unsigned total, accepted, exact, tie_even, tie_odd, carry;
static FILE *output;
static uint32_t next(void) { rng ^= rng<<13; rng ^= rng>>17; rng ^= rng<<5; return rng; }
static float as_float(uint32_t b) { float x; memcpy(&x,&b,4); return x; }
static uint32_t as_bits(float x) { uint32_t b; memcpy(&b,&x,4); return b; }

/* An integer derivation checked against host IEEE FP32 MUL, never against an
 * implementation of this same bit algorithm compiled for the DUT. */
static void emit(uint32_t a, uint32_t w) {
    const unsigned ea=(a>>23)&255, ew=(w>>23)&255;
    const int exponent=(int)ea+(int)ew-127;
    const unsigned eligible=ea>0 && ea<255 && ew>=113 && ew<=142 &&
        !(w&8191) && exponent>=1 && exponent<=252;
    uint32_t expected=0, flags=0;
    if(eligible) {
        volatile float av=as_float(a), wv=as_float(w);
        if(feclearexcept(FE_ALL_EXCEPT)) abort();
        volatile float product=av*wv;
        const int exceptions=fetestexcept(FE_ALL_EXCEPT);
        if(exceptions & ~FE_INEXACT) abort();
        expected=as_bits(product); flags=!!(exceptions&FE_INEXACT);
        const uint64_t p=(uint64_t)(0x800000u|(a&0x7fffffu))*(1024u|((w>>13)&1023));
        const unsigned norm=(unsigned)(p>>34), shift=10+norm;
        const uint64_t mask=(1ull<<shift)-1, tail=p&mask, half=1ull<<(shift-1);
        const uint32_t m=(uint32_t)(p>>shift);
        const unsigned up=tail>half || (tail==half && (m&1));
        const uint32_t rounded=m+up;
        const unsigned overflow=rounded>>24;
        const uint32_t fraction=(overflow ? rounded>>1 : rounded)&0x7fffffu;
        const uint32_t bits=((a^w)&0x80000000u)|((uint32_t)(exponent+(int)norm+(int)overflow)<<23)|fraction;
        if(bits!=expected || flags!=(tail!=0)) {
            fprintf(stderr,"MIXED_SCALE_ORACLE_FAIL a=%08x w=%08x host=%08x bits=%08x flags=%u tail=%llu\n",
                    a,w,expected,bits,flags,(unsigned long long)tail); exit(1);
        }
        ++accepted; exact+=!flags; carry+=overflow;
        tie_even+=tail==half && !(m&1); tie_odd+=tail==half && (m&1);
    }
    if(fprintf(output,"%08x %08x %u %08x %02x\n",a,w,eligible,expected,flags)<0) abort();
    ++total;
}

int main(int argc,char **argv) {
    if(argc!=2 || fesetround(FE_TONEAREST)) return 2;
    output=fopen(argv[1],"wx"); if(!output) return 2;
    const unsigned exponents[]={0,1,2,13,14,64,112,126,127,128,240,252,253,254,255};
    const unsigned fractions[]={0,1,511,512,1023};
    for(unsigned sign=0;sign<4;++sign)
        for(unsigned ew=1;ew<31;++ew)
            for(unsigned e=0;e<sizeof(exponents)/sizeof(exponents[0]);++e)
                for(unsigned f=0;f<sizeof(fractions)/sizeof(fractions[0]);++f) {
                    const uint32_t w=((sign&1)<<31)|((ew+112)<<23)|(fractions[f]<<13);
                    const uint32_t a=((sign>>1)<<31)|(exponents[e]<<23)|((f*0x200200u)&0x7fffffu);
                    emit(a,w);
                }
    emit(0x3f800200,0x3f802000); emit(0x3f800600,0x3f802000);
    /* Construct near-two products to exercise mantissa rounding carry. */
    for(unsigned m=1025;m<2048;++m) {
        const uint32_t a=(uint32_t)(((1ull<<34)-1)/m);
        emit(0x3f800000|(a&0x7fffff),0x3f800000|((m-1024)<<13));
    }
    for(unsigned i=0;i<100000;++i) {
        const uint32_t a=next(); uint32_t w=next();
        if(i%4) w=(w&0x80000000u)|((113u+(w%30))<<23)|(((w>>5)&1023)<<13);
        emit(a,w);
    }
    if(fclose(output) || accepted<50000 || !exact || !tie_even || !tie_odd || !carry) return 1;
    printf("MIXED_SCALE_ORACLE_PASS total=%u admitted=%u rejected=%u exact=%u tie_even=%u tie_odd=%u carry=%u\n",
           total,accepted,total-accepted,exact,tie_even,tie_odd,carry);
    return 0;
}
