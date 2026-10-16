#include <stdint.h>
#include "operations.h"
static uint8_t input[8192] __attribute__((aligned(64)));
static uint8_t output[8192] __attribute__((aligned(64)));
static uint8_t memory[8192] __attribute__((aligned(64)));
static uint8_t expected[8192],mask[128];
struct scene {volatile uint64_t phase,bad_index,expected,actual;};
static const unsigned fields[]={FIELDS};
extern unsigned long capacity(void);
typedef unsigned long (*operation)(const void *,void *,const void *,unsigned long,
                                   unsigned long,void *,long,void *);
static operation functions[]={FUNCTIONS};
static long syscall6(long n,long x,long y,long z,long u,long v,long w) {
    register long a0 __asm__("a0")=x,a1 __asm__("a1")=y,a2 __asm__("a2")=z,
                  a3 __asm__("a3")=u,a4 __asm__("a4")=v,a5 __asm__("a5")=w,a7 __asm__("a7")=n;
    __asm__ volatile("ecall":"+r"(a0):"r"(a1),"r"(a2),"r"(a3),"r"(a4),"r"(a5),"r"(a7):"memory");return a0;
}
static void text(const char *s) {long n=0;while(s[n])++n;syscall6(64,1,(long)s,n,0,0,0);}
static void num(uint64_t n) {char s[24];unsigned i=23;s[i]=0;do{s[--i]='0'+n%10;n/=10;}while(n);text(s+i);}
static void quit(unsigned code) {syscall6(94,code,0,0,0,0,0);for(;;){}}
void probe_main(void) {
    unsigned cap=capacity(),errors=0,cases=0,supported=0,unsupported=0,no_active=0,details=0;
    if(!cap || cap>1024){text("RVV_SEGMENT_CAP_CAPACITY_FAIL\n");quit(2);}
    long shared=syscall6(222,0,4096,3,0x21,-1,0);
    if(shared<0){text("RVV_SEGMENT_CAP_MMAP_FAIL\n");quit(2);}
    struct scene *scene=(struct scene *)shared;
    unsigned bytes=SEW/8,lengths[]={0,1,cap},offsets[]={0,1,bytes-1};
    for(unsigned op=0;op<OP_COUNT;++op)
    for(unsigned reverse=0;reverse<(op%4>=2 ? 2u:1u);++reverse)
    for(unsigned oi=0;oi<(SEW==16 ? 2u:3u);++oi)
    for(unsigned l=0;l<3;++l)for(unsigned all_off=0;all_off<2;++all_off) {
        unsigned nf=fields[op],store=op%2,offset=offsets[oi],vl=lengths[l];
        long stride=(op%4>=2 ? nf+2:nf)*bytes;
        unsigned base=64+offset+(reverse ? (cap-1)*stride:0);
        if(64+offset+(cap-1)*(nf+2)*bytes+nf*bytes>=8192 || 64+nf*cap*bytes>=8192) {
            text("RVV_SEGMENT_CAP_BOUNDS_FAIL\n");quit(2);
        }
        if(reverse)stride=-stride;
        for(unsigned i=0;i<128;++i)mask[i]=all_off ? 0:255;
        for(unsigned i=0;i<8192;++i) {
            input[i]=(i*73+(i>>4)*37)^0x85;
            memory[i]=store ? 0x5b:(uint8_t)((i*19+(i>>3)*43)^0xd3);
            output[i]=0x5b;expected[i]=store ? memory[i]:output[i];
        }
        if(!all_off)for(unsigned i=0;i<vl;++i)
            for(unsigned f=0;f<nf;++f)for(unsigned b=0;b<bytes;++b) {
                unsigned packed=64+(f*cap+i)*bytes+b,at=base+i*stride+f*bytes+b;
                if(store)expected[at]=input[packed];else expected[packed]=memory[at];
            }
        scene->phase=scene->bad_index=scene->expected=scene->actual=0;
        long child=syscall6(220,17,0,0,0,0,0);
        if(child<0){text("RVV_SEGMENT_CAP_CLONE_FAIL\n");quit(2);}
        if(!child) {
            unsigned bad=functions[op](input+64,output+64,mask,vl,cap,memory+base,stride,(void *)&scene->phase)!=0;
            const uint8_t *actual=store ? memory:output;
            for(unsigned i=0;i<8192;++i)if(actual[i]!=expected[i]) {
                if(!bad){scene->bad_index=i;scene->expected=expected[i];scene->actual=actual[i];}
                ++bad;
            }
            quit(bad ? 1:0);
        }
        unsigned status=0;
        long waited=syscall6(260,child,(long)&status,0,0,0,0);
        unsigned allowed=offset && vl && !all_off && scene->phase==1 && (status&127)==7;
        if(waited==child && !status) {
            ++supported;if(!vl || all_off)++no_active;
        } else if(waited==child && allowed)++unsupported;
        else {
            ++errors;
            if(details++<20) {
                text("RVV_SEGMENT_CAP_DETAIL op=");num(op);text(" nf=");num(nf);
                text(" offset=");num(offset);text(" vl=");num(vl);text(" all_off=");num(all_off);
                text(" reverse=");num(reverse);text(" status=");num(status);
                text(" phase=");num(scene->phase);text(" bad_byte=");num(scene->bad_index);
                text(" expected=");num(scene->expected);text(" actual=");num(scene->actual);text("\n");
            }
        }
        ++cases;
    }
    syscall6(215,shared,4096,0,0,0,0);
    text(errors ? "RVV_SEGMENT_CAP_FAIL sew=":unsupported ? "RVV_SEGMENT_CAP_UNSUPPORTED sew=":"RVV_SEGMENT_CAP_PASS sew=");num(SEW);
    text(" cases=");num(cases);text(" numerical_pass=");num(supported);
    text(" target_sigbus=");num(unsupported);text(" no_active_pass=");num(no_active);
    text(" errors=");num(errors);text("\n");quit(errors ? 1:unsupported ? 77:0);
}
__asm__(".global _start\n_start:\n.option push\n.option norelax\n"
        "la gp,__global_pointer$\n.option pop\ntail probe_main\n");
