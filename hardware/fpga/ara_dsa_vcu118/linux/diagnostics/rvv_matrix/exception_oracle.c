#include <stdint.h>
#if SEW == 8
typedef uint8_t word;
#elif SEW == 16
typedef uint16_t word;
#elif SEW == 32
typedef uint32_t word;
#else
typedef uint64_t word;
#endif
static word out[130];
static uint8_t mask[16];
extern unsigned long capacity(void),load_0(const void *,void *,const void *,unsigned long),load_1(const void *,void *,const void *,unsigned long);
static long syscall6(long n,long x,long y,long z,long u,long v,long w){
    register long a0 __asm__("a0")=x,a1 __asm__("a1")=y,a2 __asm__("a2")=z,
                  a3 __asm__("a3")=u,a4 __asm__("a4")=v,a5 __asm__("a5")=w,a7 __asm__("a7")=n;
    __asm__ volatile("ecall":"+r"(a0):"r"(a1),"r"(a2),"r"(a3),"r"(a4),"r"(a5),"r"(a7):"memory");return a0;
}
static void text(const char *s){long n=0;while(s[n])++n;syscall6(64,1,(long)s,n,0,0,0);}
static void num(uint64_t n){char s[24];unsigned i=23;s[i]=0;do{s[--i]='0'+n%10;n/=10;}while(n);text(s+i);}
static void quit(unsigned code){syscall6(94,code,0,0,0,0,0);for(;;){}}
void probe_main(void){
    unsigned cap=capacity(),errors=0,cases=0,signals=0;
#if DETAIL_SCENARIOS
    unsigned unexpected_signal[6]={0},child_failure[6]={0},wait_failure[6]={0};
#endif
    if(cap<8 || cap>128){text("RVV_EXCEPTION_CAPACITY_FAIL\n");quit(2);}
    long mapping=syscall6(222,0,8192,3,0x22,-1,0);
    if(mapping<0){text("RVV_EXCEPTION_MMAP_FAIL\n");quit(2);}
    word *start=(word *)(mapping+4096)-4;
    for(unsigned i=0;i<4;++i)start[i]=(word)(i*37+11);
    if(syscall6(226,mapping+4096,4096,0,0,0,0)){text("RVV_EXCEPTION_MPROTECT_FAIL\n");quit(2);}
    /* Expected faults execute only in children; the parent checks real wait status. */
    for(unsigned round=0;round<16;++round)for(unsigned scenario=0;scenario<6;++scenario){
        for(unsigned i=0;i<130;++i)out[i]=(word)0x5b;
        for(unsigned i=0;i<16;++i)mask[i]=0;
        mask[0]=scenario==0 || scenario==4 ? 255:scenario==1 || scenario==2 ? 15:0;
        unsigned ff=scenario==0 || scenario==2 || scenario==4 || scenario==5;
        unsigned fault=scenario==4;
        const void *address=scenario>=3 ? (void *)(mapping+4096):(void *)start;
        long child=syscall6(220,17,0,0,0,0,0);
        if(child<0){text("RVV_EXCEPTION_CLONE_FAIL\n");quit(2);}
        if(!child){
            unsigned long result=(ff ? load_1:load_0)(address,out+1,mask,8);
            unsigned want_vl=scenario==0 ? 4:8;
            unsigned bad=(uint32_t)result!=want_vl || result>>32;
            if(fault)quit(1);
            for(unsigned i=0;i<8;++i){
                if(scenario==0 && i>=4)continue;
                word wanted=scenario<3 && i<4 ? start[i]:(word)0x5b;
                if(out[i+1]!=wanted)++bad;
            }
            if(out[0]!=(word)0x5b || out[9]!=(word)0x5b)++bad;
            quit(bad ? 1:0);
        }
        unsigned status=0;
        long waited=syscall6(260,child,(long)&status,0,0,0,0);
#if DETAIL_SCENARIOS
        if(waited!=child)++wait_failure[scenario];
        else if(!fault && (status&127))++unexpected_signal[scenario];
        else if(!fault && status)++child_failure[scenario];
#endif
        if(waited!=child || (fault ? (status&127)!=11:status!=0))++errors;
        if(fault && (status&127)==11)++signals;
        ++cases;
    }
    syscall6(215,mapping,8192,0,0,0,0);
#if DETAIL_SCENARIOS
    for(unsigned scenario=0;scenario<6;++scenario){
        text("RVV_EXCEPTION_SCENARIO id=");num(scenario);
        text(" unexpected_signals=");num(unexpected_signal[scenario]);
        text(" nonzero_exits=");num(child_failure[scenario]);
        text(" wait_failures=");num(wait_failure[scenario]);text("\n");
    }
#endif
    text(errors ? "RVV_EXCEPTION_FAIL sew=":"RVV_EXCEPTION_PASS sew=");num(SEW);
    text(" cases=");num(cases);text(" expected_sigsegv=");num(signals);text(" errors=");num(errors);text("\n");quit(errors ? 1:0);
}
__asm__(".global _start\n_start:\n.option push\n.option norelax\nla gp,__global_pointer$\n.option pop\ntail probe_main\n");
