#include <stdint.h>
#include <asm/signal.h>
static uint8_t input[4096];
struct snapshot {uint64_t state[4];uint8_t bytes[4096];uint64_t guard;};
static struct snapshot output;
static volatile unsigned handled;
#if NESTED_CONTEXT
static uint8_t alternate_stack[65536] __attribute__((aligned(16)));
static uint8_t nested_input[4096];
static struct snapshot nested_output;
static volatile unsigned inner_handled;
static volatile unsigned nested_errors,nested_cases;
static volatile unsigned long *nested_ready;
static unsigned long register_bytes;
#endif
extern long context_round(const void *,void *,unsigned long,const void *,unsigned long,const void *);
static long syscall4(long n,long x,long y,long z,long u){
    register long a0 __asm__("a0")=x,a1 __asm__("a1")=y,a2 __asm__("a2")=z,a3 __asm__("a3")=u,a7 __asm__("a7")=n;
    __asm__ volatile("ecall":"+r"(a0):"r"(a1),"r"(a2),"r"(a3),"r"(a7):"memory");return a0;
}
static long shared_page(void){
    register long a0 __asm__("a0")=0,a1 __asm__("a1")=4096,a2 __asm__("a2")=3,
                  a3 __asm__("a3")=0x21,a4 __asm__("a4")=-1,a5 __asm__("a5")=0,a7 __asm__("a7")=222;
    __asm__ volatile("ecall":"+r"(a0):"r"(a1),"r"(a2),"r"(a3),"r"(a4),"r"(a5),"r"(a7):"memory");return a0;
}
static void text(const char *s){long n=0;while(s[n])++n;syscall4(64,1,(long)s,n,0);}
static void num(uint64_t n){char s[24];unsigned i=23;s[i]=0;do{s[--i]='0'+n%10;n/=10;}while(n);text(s+i);}
static void handler(int sig){
#if NESTED_CONTEXT
    volatile uint8_t stack_marker=0;
    uintptr_t address=(uintptr_t)&stack_marker;
    if(address<(uintptr_t)alternate_stack ||
       address>=(uintptr_t)alternate_stack+sizeof(alternate_stack))++nested_errors;
    if(sig==SIGUSR1){
        unsigned mode=handled%4;
        ++handled;
        for(unsigned i=0;i<4096;++i){nested_input[i]=(uint8_t)(i*19+handled*73);nested_output.bytes[i]=0x5b;}
        nested_output.guard=UINT64_C(0x5b7a83c95612e40f);
        unsigned before=inner_handled;
        long rc=context_round(nested_input,&nested_output,register_bytes,
                              (const void *)&inner_handled,mode,(const void *)nested_ready);
        const unsigned types[]={3,0xcf,0x11,0xd8};
        unsigned vl=mode==0 ? register_bytes*8-1:mode==1 ? 3:mode==2 ? 17:0;
        if(rc || inner_handled!=before+1 || nested_output.state[0]!=vl ||
           nested_output.state[1]!=types[mode] || nested_output.state[2]!=mode*2+1 ||
           nested_output.state[3])++nested_errors;
        for(unsigned i=0;i<4096;++i)
            if(nested_output.bytes[i]!=(i<32*register_bytes ? nested_input[i]:0x5b))++nested_errors;
        if(nested_output.guard!=UINT64_C(0x5b7a83c95612e40f))++nested_errors;
        ++nested_cases;
        return;
    }
    if(sig==SIGUSR2)++inner_handled;
#else
    if(sig==SIGUSR1)++handled;
#endif
    __asm__ volatile("vsetvli t0,zero,e8,m8,ta,ma\nvmv.v.i v0,-1\nvmv.v.i v8,-1\n"
                     "vmv.v.i v16,-1\nvmv.v.i v24,-1\ncsrwi vcsr,0":::
                     "t0","v0","v8","v16","v24","memory");
}
void probe_main(void){
    unsigned long vlenb;__asm__ volatile("csrr %0,vlenb":"=r"(vlenb));
    if(vlenb<64 || vlenb>128){text("RVV_CONTEXT_CAPACITY_FAIL\n");syscall4(94,2,0,0,0);for(;;){}}
    struct sigaction action={.sa_handler=handler,.sa_flags=0,.sa_mask={{0}}};
#if NESTED_CONTEXT
    register_bytes=vlenb;
    stack_t stack={.ss_sp=alternate_stack,.ss_flags=0,.ss_size=sizeof(alternate_stack)};
    if(syscall4(132,(long)&stack,0,0,0)){text("RVV_CONTEXT_ALTSTACK_FAIL\n");syscall4(94,2,0,0,0);for(;;){}}
    action.sa_flags=SA_ONSTACK;
    if(syscall4(134,SIGUSR2,(long)&action,0,sizeof(action.sa_mask))){text("RVV_CONTEXT_SIGACTION_FAIL\n");syscall4(94,2,0,0,0);for(;;){}}
#endif
    if(syscall4(134,SIGUSR1,(long)&action,0,sizeof(action.sa_mask))){text("RVV_CONTEXT_SIGACTION_FAIL\n");syscall4(94,2,0,0,0);for(;;){}}
    long pid=syscall4(172,0,0,0,0);
    long page=shared_page();
    if(page<0){text("RVV_CONTEXT_MMAP_FAIL\n");syscall4(94,2,0,0,0);for(;;){}}
    volatile unsigned long *ready=(void *)page;
#if NESTED_CONTEXT
    nested_ready=ready+1;
#endif
    unsigned errors=0,cases=0;
    const unsigned types[]={3,0xcf,0x11,0xd8};
    for(unsigned round=0;round<32;++round)for(unsigned mode=0;mode<4;++mode){
        for(unsigned i=0;i<32*vlenb;++i){input[i]=(uint8_t)(i*37+round*11+mode*71);output.bytes[i]=0x5b;}
        for(unsigned i=32*vlenb;i<4096;++i)output.bytes[i]=0x5b;
        output.guard=UINT64_C(0x5b7a83c95612e40f);
        unsigned before=handled;
        *ready=0;
#if NESTED_CONTEXT
        *nested_ready=0;
#endif
        long child=syscall4(220,17,0,0,0);
        if(child<0){text("RVV_CONTEXT_CLONE_FAIL\n");syscall4(94,2,0,0,0);for(;;){}}
        if(!child){
            while(!*ready){}
            long sent=syscall4(129,pid,SIGUSR1,0,0);
#if NESTED_CONTEXT
            if(!sent){while(!*nested_ready){}sent=syscall4(129,pid,SIGUSR2,0,0);}
#endif
            syscall4(94,sent ? 2:0,0,0,0);for(;;){}
        }
        long rc=context_round(input,&output,vlenb,(const void *)&handled,mode,(const void *)ready);
        if(rc || handled!=before+1)++errors;
        unsigned vl=mode==0 ? vlenb*8-1:mode==1 ? 3:mode==2 ? 17:0;
        if(output.state[0]!=vl || output.state[1]!=types[mode] || output.state[2]!=(mode*2+1) || output.state[3])++errors;
        for(unsigned i=0;i<4096;++i)if(output.bytes[i]!=(i<32*vlenb ? input[i]:0x5b))++errors;
        if(output.guard!=UINT64_C(0x5b7a83c95612e40f))++errors;
        unsigned status=0;
        if(syscall4(260,child,(long)&status,0,0)!=child || status)++errors;
        ++cases;
    }
#if NESTED_CONTEXT
    if(inner_handled!=cases || nested_cases!=cases)++errors;
    errors+=nested_errors;
    cases+=nested_cases;
#endif
    text(errors ? "RVV_CONTEXT_FAIL cases=":"RVV_CONTEXT_PASS cases=");num(cases);
    text(" signals=");num(handled);text(" errors=");num(errors);text("\n");syscall4(94,errors ? 1:0,0,0,0);for(;;){}
}
__asm__(".global _start\n_start:\n.option push\n.option norelax\nla gp,__global_pointer$\n.option pop\ntail probe_main\n");
