/* Host-only reference adapter; arithmetic is Berkeley SoftFloat, not native FP. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "softfloat.h"
#ifndef OP_COUNT
#define OP_COUNT 13
#endif
#ifndef SCALAR_FORMS
#define SCALAR_FORMS 0
#endif
#ifndef SCALAR_EXTRAS
#define SCALAR_EXTRAS 0
#endif
#ifndef DESTRUCTIVE_FMA
#define DESTRUCTIVE_FMA 0
#endif
static unsigned classify(uint64_t bits,unsigned width){
    unsigned fraction=width==16 ? 10:width==32 ? 23:52;
    unsigned exponent=width==16 ? 5:width==32 ? 8:11;
    unsigned negative=bits>>(width-1);
    uint64_t e=(bits>>fraction)&((1u<<exponent)-1);
    uint64_t f=bits&((UINT64_C(1)<<fraction)-1);
    if(e==((1u<<exponent)-1))return f ? 1u<<((f>>(fraction-1)) ? 9:8):1u<<(negative ? 0:7);
    if(!e)return 1u<<(f ? (negative ? 2:5):(negative ? 3:4));
    return 1u<<(negative ? 1:6);
}
static const uint64_t raw16[]={0,0x8000,0x3c00,0xbc00,0x3800,0x4000,0x4200,
    0x1000,1,0x03ff,0x0400,0x7bff,0x7c00,0xfc00,0x7e55,0x7c55};
static const uint64_t raw32[]={0,0x80000000,0x3f800000,0xbf800000,0x3f000000,
    0x40000000,0x40400000,0x33800000,1,0x007fffff,0x00800000,0x7f7fffff,
    0x7f800000,0xff800000,0x7fc12345,0x7f812345};
static const uint64_t raw64[]={0,UINT64_C(0x8000000000000000),UINT64_C(0x3ff0000000000000),
    UINT64_C(0xbff0000000000000),UINT64_C(0x3fe0000000000000),UINT64_C(0x4000000000000000),
    UINT64_C(0x4008000000000000),UINT64_C(0x3ca0000000000000),1,UINT64_C(0x000fffffffffffff),
    UINT64_C(0x0010000000000000),UINT64_C(0x7fefffffffffffff),UINT64_C(0x7ff0000000000000),
    UINT64_C(0xfff0000000000000),UINT64_C(0x7ff8123456789abc),UINT64_C(0x7ff0123456789abc)};
#define CALCULATE(W,TYPE,RAW,IW) \
    TYPE a={RAW[i%16]},b={RAW[SCALAR_FORMS ? scalar_index:(i*3+i/16*5)%16]},c={RAW[(i*7+11)%16]},r; \
    unsigned selected_op=DESTRUCTIVE_FMA ? 23+op:SCALAR_EXTRAS ? 16+op:SCALAR_FORMS && op>=4 ? op+1:op; \
    if(selected_op==15 && i>=16)a.v^=(uint##W##_t)1<<(W-1); \
    uint64_t result=0; \
    switch(selected_op){ \
    case 0:r=f##W##_add(a,b);result=r.v;break; \
    case 1:r=f##W##_sub(a,b);result=r.v;break; \
    case 2:r=f##W##_mul(a,b);result=r.v;break; \
    case 3:r=f##W##_div(a,b);result=r.v;break; \
    case 4:r=f##W##_sqrt(a);result=r.v;break; \
    case 5:case 6:case 7:case 8: \
        if(selected_op==7 || selected_op==8)a.v^=(uint##W##_t)1<<(W-1); \
        if(selected_op==6 || selected_op==7)c.v^=(uint##W##_t)1<<(W-1); \
        r=f##W##_mulAdd(a,b,c);result=r.v;break; \
    case 9:result=f##W##_to_i##W(a,softfloat_roundingMode,1);break; \
    case 10:result=f##W##_to_ui##W(a,softfloat_roundingMode,1);break; \
    case 11:r=i##IW##_to_f##W((int##W##_t)a.v);result=r.v;break; \
    case 12:r=ui##IW##_to_f##W(a.v);result=r.v;break; \
    case 13:result=f##W##_to_i##W(a,softfloat_round_minMag,1);break; \
    case 14:result=f##W##_to_ui##W(a,softfloat_round_minMag,1);break; \
    case 16:r=f##W##_sub(b,a);result=r.v;break; \
    case 17:r=f##W##_div(b,a);result=r.v;break; \
    case 18:r=f##W##_min(a,b);result=r.v;break; \
    case 19:r=f##W##_max(a,b);result=r.v;break; \
    case 20:result=(a.v & ~((uint##W##_t)1<<(W-1))) | (b.v & ((uint##W##_t)1<<(W-1)));break; \
    case 21:result=(a.v & ~((uint##W##_t)1<<(W-1))) | ((~b.v) & ((uint##W##_t)1<<(W-1)));break; \
    case 22:result=a.v ^ (b.v & ((uint##W##_t)1<<(W-1)));break; \
    case 23:case 24:case 25:case 26:{ \
        TYPE multiplier=SCALAR_FORMS ? b:a,addend=SCALAR_FORMS ? a:b; \
        if(selected_op==25 || selected_op==26)c.v^=(uint##W##_t)1<<(W-1); \
        if(selected_op==24 || selected_op==25)addend.v^=(uint##W##_t)1<<(W-1); \
        r=f##W##_mulAdd(c,multiplier,addend);result=r.v;break;} \
    default:result=classify(a.v,W);break; \
    } \
    result=(uint##W##_t)result; \
    printf("[%llu,%u]",(unsigned long long)result,(unsigned)softfloat_exceptionFlags)
int main(int argc,char **argv){
    if(argc!=2 && !(SCALAR_FORMS && argc==3))return 2;
    unsigned width=strtoul(argv[1],0,10);
    unsigned scalar_index=SCALAR_FORMS && argc==3 ? strtoul(argv[2],0,10):4;
    if(scalar_index>=16)return 2;
    if(width!=16 && width!=32 && width!=64)return 2;
    const unsigned modes[]={0,1,2,3,4};
    printf("[");
    for(unsigned rm=0;rm<5;++rm){if(rm)printf(",");printf("[");
        for(unsigned op=0;op<OP_COUNT;++op){if(op)printf(",");printf("[");
            for(unsigned i=0;i<32;++i){if(i)printf(",");softfloat_roundingMode=modes[rm];softfloat_exceptionFlags=0;
                if(width==16){CALCULATE(16,float16_t,raw16,32);}
                else if(width==32){CALCULATE(32,float32_t,raw32,32);}
                else{CALCULATE(64,float64_t,raw64,64);}}
            printf("]");}printf("]");}
    puts("]");return 0;
}
