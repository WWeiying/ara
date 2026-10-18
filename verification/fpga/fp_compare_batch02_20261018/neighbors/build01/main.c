#include <stdint.h>
#include <stddef.h>
extern void replay_text(const char *);
extern int replay_mismatch(unsigned long,unsigned long,unsigned long,unsigned long);
extern volatile unsigned long replay_case;
typedef unsigned long (*operation)(const void *,const void *,const void *,const void *,void *);
struct test { operation run; unsigned op,dest,triple,masked,start,vl,mixed,carry,context; };
extern unsigned long neighbor_0(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_1(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_2(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_3(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_4(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_5(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_6(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_7(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_8(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_9(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_10(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_11(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_12(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_13(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_14(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_15(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_16(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_17(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_18(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_19(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_20(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_21(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_22(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_23(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_24(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_25(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_26(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_27(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_28(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_29(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_30(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_31(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_32(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_33(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_34(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_35(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_36(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_37(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_38(const void *,const void *,const void *,const void *,void *);
extern unsigned long neighbor_39(const void *,const void *,const void *,const void *,void *);
static const struct test tests[] = {
    {neighbor_0,0,8,0,1,3,37,0,0,0},
    {neighbor_1,0,16,0,1,3,37,0,0,0},
    {neighbor_2,0,8,1,1,3,37,0,0,0},
    {neighbor_3,1,8,0,1,3,37,0,0,0},
    {neighbor_4,1,16,0,1,3,37,0,0,0},
    {neighbor_5,1,8,1,1,3,37,0,0,0},
    {neighbor_6,2,8,0,1,3,37,0,0,0},
    {neighbor_7,2,16,0,1,3,37,0,0,0},
    {neighbor_8,2,8,1,1,3,37,0,0,0},
    {neighbor_9,3,8,0,1,3,37,0,0,0},
    {neighbor_10,3,16,0,1,3,37,0,0,0},
    {neighbor_11,3,8,1,1,3,37,0,0,0},
    {neighbor_12,4,24,0,0,1,63,0,0,0},
    {neighbor_13,4,24,0,0,1,63,0,1,0},
    {neighbor_14,5,24,0,0,1,63,0,0,0},
    {neighbor_15,5,24,0,0,1,63,0,1,0},
    {neighbor_16,0,24,0,0,0,64,0,0,0},
    {neighbor_17,3,24,0,0,0,64,0,0,0},
    {neighbor_18,3,8,0,1,33,61,1,0,0},
    {neighbor_19,3,16,0,1,33,61,1,0,0},
    {neighbor_20,0,8,0,1,3,37,0,0,1},
    {neighbor_21,0,16,0,1,3,37,0,0,1},
    {neighbor_22,0,8,1,1,3,37,0,0,1},
    {neighbor_23,1,8,0,1,3,37,0,0,1},
    {neighbor_24,1,16,0,1,3,37,0,0,1},
    {neighbor_25,1,8,1,1,3,37,0,0,1},
    {neighbor_26,2,8,0,1,3,37,0,0,1},
    {neighbor_27,2,16,0,1,3,37,0,0,1},
    {neighbor_28,2,8,1,1,3,37,0,0,1},
    {neighbor_29,3,8,0,1,3,37,0,0,1},
    {neighbor_30,3,16,0,1,3,37,0,0,1},
    {neighbor_31,3,8,1,1,3,37,0,0,1},
    {neighbor_32,4,24,0,0,1,63,0,0,1},
    {neighbor_33,4,24,0,0,1,63,0,1,1},
    {neighbor_34,5,24,0,0,1,63,0,0,1},
    {neighbor_35,5,24,0,0,1,63,0,1,1},
    {neighbor_36,0,24,0,0,0,64,0,0,1},
    {neighbor_37,3,24,0,0,0,64,0,0,1},
    {neighbor_38,3,8,0,1,33,61,1,0,1},
    {neighbor_39,3,16,0,1,33,61,1,0,1},
};
static uint32_t a[64] __attribute__((aligned(64)));
static uint32_t b[64] __attribute__((aligned(64)));
static uint8_t old[128] __attribute__((aligned(64)));
static uint8_t mask[128] __attribute__((aligned(64)));
static uint8_t output[10] __attribute__((aligned(64)));
static const uint32_t values[] = {0,1,0xffffffffU,0x80000000U,0x7fffffffU,
    0xfffffffeU,0x12345678U,0x87654321U};
static unsigned bit(const uint8_t *p,unsigned i) { return (p[i/8]>>(i%8))&1; }
static unsigned wanted(const struct test *t,unsigned i) {
    uint32_t x=a[i], y=t->triple ? a[i] : b[i];
    unsigned carry=t->carry ? bit(mask,i):0;
    switch(t->op) {
    case 0: return x==y;
    case 1: return x!=y;
    case 2: return (int32_t)x<(int32_t)y;
    case 3: return x<y;
    case 4: return (((uint64_t)x+y+carry)>>32)&1;
    default: return (uint64_t)x<((uint64_t)y+carry);
    }
}
static unsigned validate(const struct test *t,unsigned long status) {
    const uint8_t *prior=t->dest==8 ? (const uint8_t *)a:
                         t->dest==16 ? (const uint8_t *)b:old;
    unsigned errors=status!=((unsigned long)1<<32);
    errors+=output[0]!=0x5b || output[9]!=0x5b;
    for(unsigned i=0;i<64;++i) {
        unsigned actual=bit(output+1,i), before=bit(prior,i), expected=wanted(t,i);
        unsigned active=i>=t->start && i<t->vl && (!t->masked || bit(mask,i));
        if(active) errors+=actual!=expected;
        else if(i<t->start) errors+=actual!=before;
        else if(i<t->vl) {
            /* Different-EEW compare aliases permit mask-agnostic ones. */
            errors+=actual!=before && !(t->dest!=24 && actual==1);
        } else {
            /* Mask tails may retain old bits, become ones, or compute to VLMAX. */
            errors+=actual!=before && actual!=1 && actual!=expected;
        }
    }
    return errors;
}
int main(void) {
    unsigned long vlenb;
    __asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
    if(vlenb!=128) return 90;
    unsigned negatives=0;
    for(unsigned n=0;n<sizeof(tests)/sizeof(tests[0]);++n) {
        const struct test *t=tests+n;
        replay_case=n;
        for(unsigned i=0;i<64;++i) {
            a[i]=values[(i*5+i/8)%8]; b[i]=values[(i*3+2+i/7)%8];
        }
        for(unsigned i=0;i<128;++i) {old[i]=(uint8_t)(0x5b^(i*13));mask[i]=0xaa;}
        for(unsigned i=0;i<10;++i) output[i]=0x5b;
        unsigned long status=t->run(a,b,old,mask,output+1);
        unsigned errors=validate(t,status);
        if(errors) return replay_mismatch(n,0,0,errors);
        unsigned active=t->start;
        while(t->masked && !bit(mask,active)) ++active;
        output[1+active/8]^=1U<<(active%8);
        if(!validate(t,status)) return 91;
        ++negatives;
        output[1+active/8]^=1U<<(active%8);
        if(!validate(t,status^((unsigned long)16<<32))) return 92;
        ++negatives;
        output[0]^=1;
        if(!validate(t,status)) return 93;
        ++negatives;
        output[0]^=1;
        if(validate(t,status)) return 94;
    }
    if(negatives!=120) return 95;
    replay_text("NEIGHBORS_INTEGER_PASS cases=40 errors=0\n");
    replay_text("NEIGHBORS_ORACLE_NEGATIVE_PASS checks=120\n");
    replay_text("BOARD_REPLAY_PASS\n");
    return 0;
}
