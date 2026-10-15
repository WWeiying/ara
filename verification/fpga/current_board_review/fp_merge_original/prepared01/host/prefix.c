#include <stdint.h>
#include "operations.h"
#ifndef RESTART_MOVES
#define RESTART_MOVES 0
#endif
#ifndef MOVE_OP_MASK
#define MOVE_OP_MASK 255U
#endif
#if SEW == 16
typedef uint16_t word;
#define CANONICAL_NAN UINT64_C(0x7e00)
#elif SEW == 32
typedef uint32_t word;
#define CANONICAL_NAN UINT64_C(0x7fc00000)
#else
typedef uint64_t word;
#define CANONICAL_NAN UINT64_C(0x7ff8000000000000)
#endif
#include "inputs.h"
static word a[1024],output[1026];
static uint8_t mask[128];
extern unsigned long capacity(void);
typedef unsigned long (*operation)(const void *,const void *,void *,unsigned long,
                                   unsigned long,const void *,unsigned long,void *);
static operation functions[]={FUNCTIONS};
extern long replay_write(long,long,long,long);
#define syscall3 replay_write
static void text(const char *s) {long n=0;while(s[n])++n;syscall3(64,1,(long)s,n);}
static void num(uint64_t n) {char s[24];unsigned i=23;s[i]=0;do{s[--i]='0'+n%10;n/=10;}while(n);text(s+i);}
static unsigned selected(unsigned i) {return (mask[i/8]>>(i%8))&1;}
static uint64_t boxed(word value) {
#if SEW < 64
    return (UINT64_MAX-((UINT64_C(1)<<SEW)-1))|(uint64_t)value;
#else
    return value;
#endif
}
int fp_merge_prefix195_main(void) {
    unsigned cap=capacity(),errors=0,cases=0,details=0;
    if(!cap || cap>1024){text("RVV_FP_MOVE_CAPACITY_FAIL\n");return 2;}
    unsigned lengths[]={0,1,2,3,cap/2,cap-1,cap};
    for(unsigned seed=0;seed<3;++seed)for(unsigned scalar=0;scalar<16;++scalar)
    for(unsigned invalid=0;invalid<(SEW==64 ? 1u:2u);++invalid)
    for(unsigned op=0;op<8;++op)for(unsigned l=0;l<7;++l)
    for(unsigned mode=0;mode<4;++mode)
    for(unsigned st=0;st<(RESTART_MOVES ? 4u:1u);++st)
    for(unsigned sticky=0;sticky<2;++sticky) {
        if(!(MOVE_OP_MASK & (1U<<op)))continue;
        unsigned prior=errors,vl=lengths[l];
        unsigned start=RESTART_MOVES ? (st==0 ? 1:st==1 ? vl/2:st==2 ? vl:cap-1):0;
        uint64_t scalar_bits=invalid ? (uint64_t)inputs[scalar]:boxed(inputs[scalar]);
        word scalar_value=invalid ? (word)CANONICAL_NAN:inputs[scalar];
        uint64_t scalar_result=UINT64_C(0x123456789abcdef0);
        for(unsigned i=0;i<128;++i)
            mask[i]=mode==0 ? 255:mode==1 ? 0xaa:mode==2 ? 0x24:0;
        for(unsigned i=0;i<cap;++i) {
            a[i]=inputs[(i+seed*7)%16];
            output[i+1]=inputs[(i*3+seed*5+11)%16];
        }
        output[0]=output[cap+1]=(word)0x5b;
        if(RESTART_MOVES && seed==0 && scalar==0 && invalid==0 && op==0 && mode==0 && sticky==0) {
            text("RVV_FP_MOVE_TRIAL vl=");num(vl);text(" vstart=");num(start);
            text(" completed=");num(cases);text("\n");
            if(0 /* No Linux tty drain in bare metal. */) {
                text("RVV_FP_MOVE_TRACE_DRAIN_FAILED\n");return 2;
            }
        }
        unsigned long control=RESTART_MOVES ? ((uint64_t)sticky<<32)|start:sticky;
        unsigned long status=functions[op](a,&scalar_bits,output+1,vl,cap,mask,control,&scalar_result);
        if((uint32_t)status || (status>>32)!=sticky)++errors;
#if DETAIL_MOVES
        unsigned first_bad=cap;
        word first_wanted=0,first_actual=0;
#endif
        for(unsigned i=0;i<cap;++i) {
            word wanted=inputs[(i*3+seed*5+11)%16];
            /* Scalar insertion ignores the element start, but not start>=VL. */
            if(op==6 && start<vl && i==0)wanted=scalar_value;
            else if(i>=start && i<vl) {
                if(op==0)wanted=selected(i) ? scalar_value:a[i];
                else if(op==1)wanted=scalar_value;
                else if(op>=2 && op<=5 && (op>=4 || selected(i))) {
                    if(op==2 || op==4)wanted=i ? a[i-1]:scalar_value;
                    else wanted=i+1<vl ? a[i+1]:scalar_value;
                }
            }
            if(output[i+1]!=wanted) {
                ++errors;
#if DETAIL_MOVES
                if(first_bad==cap) {
                    first_bad=i;first_wanted=wanted;first_actual=output[i+1];
                }
#endif
            }
        }
        uint64_t wanted_scalar=op==7 ? boxed(a[0]):UINT64_C(0x123456789abcdef0);
        if(scalar_result!=wanted_scalar)++errors;
        if(output[0]!=(word)0x5b || output[cap+1]!=(word)0x5b)++errors;
        if(errors!=prior && details++<20) {
            text("RVV_FP_MOVE_DETAIL op=");num(op);text(" seed=");num(seed);
            text(" scalar=");num(scalar);text(" invalid_box=");num(invalid);
            text(" vl=");num(vl);text(" mask=");num(mode);text(" sticky=");num(sticky);
            text(" vstart=");num(start);
            text(" actual_flags=");num(status>>32);text(" errors=");num(errors-prior);text("\n");
#if DETAIL_MOVES
            text("RVV_FP_MOVE_CLASSIFY returned_vstart=");num((uint32_t)status);
            text(" first_bad_element=");num(first_bad);
            text(" expected_bits=");num(first_wanted);text(" actual_bits=");num(first_actual);
            text(" scalar_expected=");num(wanted_scalar);text(" scalar_actual=");num(scalar_result);
            text(" guard_before=");num(output[0]);text(" guard_after=");num(output[cap+1]);text("\n");
#endif
        }
        ++cases;
        if(cases==195)goto prefix_done;
    }
prefix_done:
    text(errors ? "RVV_FP_MOVE_FAIL sew=":"RVV_FP_MOVE_PASS sew=");num(SEW);
    text(" cases=");num(cases);text(" errors=");num(errors);text("\n");
    return errors ? 1:0;
}

#include <stdio.h>
#include <stdlib.h>

static FILE *capture;
static unsigned calls, injected;
unsigned long capacity(void) { return 512; }
long replay_write(long n, long fd, long p, long z) {
    if (n != 64 || fd != 1 || z < 0) abort();
    return fwrite((void *)p, 1, z, stdout);
}

static unsigned long emulate(unsigned op, const void *aa, const void *ss,
        void *oo, unsigned long vl, unsigned long cap, const void *mm,
        unsigned long control, void *result) {
    const uint16_t *a = aa;
    const uint8_t *m = mm;
    uint16_t *o = oo;
    uint64_t scalar = *(const uint64_t *)ss;
    unsigned start = (uint32_t)control, flags = control >> 32;
    if (op != 0 || cap != 512) abort();
    if (calls < 195 && capture) {
        uint64_t header[] = {op, vl, cap, control, scalar, *(uint64_t *)result};
        if (fwrite(header, sizeof(header), 1, capture) != 1 ||
            fwrite(a, cap * sizeof(*a), 1, capture) != 1 ||
            fwrite(o - 1, (cap + 2) * sizeof(*o), 1, capture) != 1 ||
            fwrite(m, 128, 1, capture) != 1) abort();
    }
    /* Bit-move model: no host floating-point arithmetic or shared oracle helper. */
    uint16_t value = (scalar >> 16) == UINT64_C(0xffffffffffff) ?
                     (uint16_t)scalar : UINT16_C(0x7e00);
    for (unsigned i = start; i < vl; ++i)
        o[i] = ((m[i / 8] >> (i % 8)) & 1) ? value : a[i];
    unsigned returned_start = 0;
    if (!injected) {
        if (HOST_MUTATION == 1 && start < vl) { o[start] ^= 1; injected = 1; }
        if (HOST_MUTATION == 2 && start) { o[0] ^= 1; injected = 1; }
        if (HOST_MUTATION == 3 && start < vl && vl < cap) { o[vl] ^= 1; injected = 1; }
        if (HOST_MUTATION == 4) {
            for (unsigned i = start; i < vl; ++i)
                if (!((m[i / 8] >> (i % 8)) & 1)) {
                    o[i] ^= 1; injected = 1; break;
                }
        }
        if (HOST_MUTATION == 5) { o[-1] ^= 1; injected = 1; }
        if (HOST_MUTATION == 6) { o[cap] ^= 1; injected = 1; }
        if (HOST_MUTATION == 7) { returned_start = 1; injected = 1; }
        if (HOST_MUTATION == 8) { flags ^= 16; injected = 1; }
        if (HOST_MUTATION == 9) { *(uint64_t *)result ^= 1; injected = 1; }
    }
    ++calls;
    return ((uint64_t)flags << 32) | returned_start;
}

#define OP(N) unsigned long op_##N(const void *a, const void *s, void *o, \
    unsigned long vl, unsigned long cap, const void *m, unsigned long c, void *r) { \
    return emulate(N, a, s, o, vl, cap, m, c, r); }
OP(0) OP(1) OP(2) OP(3) OP(4) OP(5) OP(6) OP(7)

int main(int argc, char **argv) {
    if (argc == 2) {
        capture = fopen(argv[1], "wbx");
        if (!capture) abort();
    } else if (argc != 1) abort();
    int status = fp_merge_prefix195_main();
    if (capture && fclose(capture)) abort();
    if (HOST_MUTATION && !injected) abort();
    if (calls != HOST_CALLS) abort();
    return status;
}
