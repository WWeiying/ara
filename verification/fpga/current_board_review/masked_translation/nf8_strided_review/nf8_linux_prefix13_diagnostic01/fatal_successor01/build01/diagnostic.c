#include <stdint.h>
#include <stddef.h>
#include <asm/signal.h>
#include <asm/siginfo.h>
#include <asm/sigcontext.h>
#include <asm/ucontext.h>
#ifndef INDEXED_REPLAY
#define INDEXED_REPLAY 0
#endif
#ifndef STRIDED_REPLAY
#define STRIDED_REPLAY 0
#endif
#ifndef NEGATIVE_STRIDE
#define NEGATIVE_STRIDE 0
#endif
#ifndef ZERO_STRIDE
#define ZERO_STRIDE 0
#endif
#ifndef NEGATIVE_SKIP
#define NEGATIVE_SKIP 0
#endif
#if NEGATIVE_STRIDE
#define PROTECTED_PAGE mapping
#else
#define PROTECTED_PAGE (mapping+4096)
#endif
#ifndef REPLAY_ELEMENTS
#define REPLAY_ELEMENTS 8
#endif
#if SEW == 8
typedef uint8_t word;
#elif SEW == 16
typedef uint16_t word;
#elif SEW == 32
typedef uint32_t word;
#else
typedef uint64_t word;
#endif
#ifndef INDEX_SEW
#define INDEX_SEW SEW
#endif
#if INDEX_SEW == 8
typedef uint8_t index_word;
#elif INDEX_SEW == 16
typedef uint16_t index_word;
#elif INDEX_SEW == 32
typedef uint32_t index_word;
#else
typedef uint64_t index_word;
#endif
#ifndef LMUL_NUM
#define LMUL_NUM 1
#define LMUL_DEN 1
#define LMUL_CODE 0
#endif
#define CAPACITY_LIMIT (128*LMUL_NUM)
#ifndef REPLAY_FIELDS
#define REPLAY_FIELDS 1
#endif
#define FIELD_REGISTER_STRIDE (LMUL_NUM>LMUL_DEN ? LMUL_NUM/LMUL_DEN:1)
_Static_assert(REPLAY_FIELDS*LMUL_NUM<=8*LMUL_DEN,"Legal segment EMUL");
_Static_assert(24+REPLAY_FIELDS*FIELD_REGISTER_STRIDE<=32,"Segment register bounds");
static word input[CAPACITY_LIMIT*REPLAY_FIELDS],output[CAPACITY_LIMIT*REPLAY_FIELDS+2];
static index_word offsets[CAPACITY_LIMIT];
static uint8_t mask[CAPACITY_LIMIT/8];
static volatile unsigned faults,handler_errors;
static unsigned cap,store_case,unmapped,expected_start;
static uintptr_t mapping,target,expected_address;
#if STRIDED_REPLAY
static long stride;
#endif
extern unsigned long capacity(void),replay_0(const void *,const void *,void *,const void *,unsigned long,const void *),
                     replay_1(const void *,const void *,void *,const void *,unsigned long,const void *);
extern char fault_0_pc[],fault_1_pc[];
#include "diagnostic.h"
static long call(long n,long x,long y,long z,long u,long v,long w){
    register long a0 __asm__("a0")=x,a1 __asm__("a1")=y,a2 __asm__("a2")=z,
                  a3 __asm__("a3")=u,a4 __asm__("a4")=v,a5 __asm__("a5")=w,a7 __asm__("a7")=n;
    __asm__ volatile("ecall":"+r"(a0):"r"(a1),"r"(a2),"r"(a3),"r"(a4),"r"(a5),"r"(a7):"memory");return a0;
}
static void text(const char *s){if(diag_in_handler){if(diag_trial<DIAG_CASES && !diagnostics[diag_trial].fatal_message)diagnostics[diag_trial].fatal_message=s;return;}long n=0;while(s[n])++n;call(64,1,(long)s,n,0,0,0);}
static void num(uint64_t n){char s[24];unsigned i=23;s[i]=0;do{s[--i]='0'+n%10;n/=10;}while(n);text(s+i);}
static void quit(unsigned code){if(diag_in_handler && code)diag_fatal_emit(code,faults,handler_errors);call(94,code,0,0,0,0,0);for(;;){}}
static unsigned active(unsigned i){return (mask[i/8]>>(i%8))&1;}
static word original(uintptr_t address){return (word)(((address-mapping)/sizeof(word))*37+11);}
static word poison(unsigned i){return (word)(input[i]^0x5b);}
static uintptr_t element_address(unsigned i){
#if STRIDED_REPLAY
    return target+i*stride;
#else
    return target+(INDEXED_REPLAY ? offsets[i]:i*REPLAY_FIELDS*sizeof(word));
#endif
}
static uintptr_t field_address(unsigned i,unsigned field){return element_address(i)+field*sizeof(word);}
static unsigned logical_element(uintptr_t address){
    for(unsigned i=0;i<REPLAY_ELEMENTS;++i)for(unsigned f=0;f<REPLAY_FIELDS;++f)
        if(field_address(i,f)==address
#if ZERO_STRIDE
           && active(i)
#endif
          )return i*REPLAY_FIELDS+f;
    return REPLAY_ELEMENTS*REPLAY_FIELDS;
}
static void fill(uintptr_t page){
    for(unsigned i=0;i<4096/sizeof(word);++i)((word *)page)[i]=original(page+i*sizeof(word));
}
static void restore_page(void){
    if(unmapped){
        if(call(222,PROTECTED_PAGE,4096,3,0x32,-1,0)!=(long)PROTECTED_PAGE){
            text("RVV_FAULT_REPLAY_REMAP_FAIL\n");quit(2);
        }
        fill(PROTECTED_PAGE);
    }else if(call(226,PROTECTED_PAGE,4096,3,0,0,0)){
        text("RVV_FAULT_REPLAY_MPROTECT_FAIL\n");quit(2);
    }
}
static void handler(int sig,siginfo_t *info,void *context){
    diag_in_handler=1;diag_signal(sig,info,(const struct ucontext *)context);
#if TRACE_REPLAY
    text("RVV_REPLAY_HANDLER sig=");num(sig);text(" context=");num((uintptr_t)context);text("\n");
#endif
    if(++faults>1){text("RVV_FAULT_REPLAY_REPEAT_FAULT\n");quit(2);}
    struct ucontext *uc=context;
    struct __riscv_ctx_hdr *hdr=&uc->uc_mcontext.sc_extdesc.hdr;
#if TRACE_REPLAY
    text("RVV_REPLAY_HEADER magic=");num(hdr->magic);text(" size=");num(hdr->size);text("\n");
#endif
    struct __riscv_v_ext_state *state=0;
    /* Signal records have bounded sizes; do not trust an unchecked datap. */
    for(unsigned count=0;count<16 && hdr->magic!=END_MAGIC;++count){
        if(hdr->size<sizeof(*hdr) || hdr->size>131072)break;
        if(hdr->magic==RISCV_V_MAGIC){
            if(hdr->size>=sizeof(*hdr)+sizeof(struct __sc_riscv_v_state))
                state=&((struct __sc_riscv_v_state *)(hdr+1))->v_state;
            break;
        }
        hdr=(void *)((uintptr_t)hdr+hdr->size);
    }
    diag_state(state);
    if(!state || state->vlenb*LMUL_NUM!=cap*sizeof(word)*LMUL_DEN ||
       (uintptr_t)state->datap<(uintptr_t)(hdr+1)+sizeof(struct __sc_riscv_v_state) ||
       (uintptr_t)state->datap>(uintptr_t)hdr+hdr->size ||
       32*state->vlenb>(uintptr_t)hdr+hdr->size-(uintptr_t)state->datap){
        text("RVV_FAULT_REPLAY_SIGNAL_FRAME_FAIL\n");quit(2);
    }
    diagnostics[diag_trial].frame_valid=1;
    unsigned address_matches=0;
    for(unsigned f=0;f<REPLAY_FIELDS;++f)
        if((uintptr_t)info->si_addr==expected_address+f*sizeof(word) &&
#if NEGATIVE_STRIDE
           (uintptr_t)info->si_addr>=mapping && (uintptr_t)info->si_addr<mapping+4096)address_matches=1;
#else
           (uintptr_t)info->si_addr>=mapping+4096)address_matches=1;
#endif
    if(sig!=SIGSEGV || !address_matches ||
       info->si_code!=(unmapped ? SEGV_MAPERR:SEGV_ACCERR) ||
       uc->uc_mcontext.sc_regs.pc!=(uintptr_t)(store_case ? fault_1_pc:fault_0_pc) ||
       state->vstart!=expected_start || state->vl!=REPLAY_ELEMENTS ||
       state->vtype!=((SEW==8 ? 0:SEW==16 ? 8:SEW==32 ? 16:24)|LMUL_CODE)){
        ++handler_errors;
        if(sig!=SIGSEGV)diag_error(E_SIGNAL,0,0,sig,SIGSEGV);
        else if(!address_matches)diag_error(E_ADDRESS,0,0,(uintptr_t)info->si_addr,expected_address);
        else if(info->si_code!=(unmapped ? SEGV_MAPERR:SEGV_ACCERR))diag_error(E_CODE,0,0,info->si_code,unmapped ? SEGV_MAPERR:SEGV_ACCERR);
        else if(uc->uc_mcontext.sc_regs.pc!=(uintptr_t)(store_case ? fault_1_pc:fault_0_pc))diag_error(E_PC,0,0,uc->uc_mcontext.sc_regs.pc,(uintptr_t)(store_case ? fault_1_pc:fault_0_pc));
        else if(state->vstart!=expected_start)diag_error(E_VSTART,0,0,state->vstart,expected_start);
        else if(state->vl!=REPLAY_ELEMENTS)diag_error(E_VL,0,0,state->vl,REPLAY_ELEMENTS);
        else diag_error(E_VTYPE,0,0,state->vtype,((SEW==8 ? 0:SEW==16 ? 8:SEW==32 ? 16:24)|LMUL_CODE));
    }
    for(unsigned f=0;f<REPLAY_FIELDS;++f){
    const word *saved=(const void *)((uintptr_t)state->datap+(24+f*FIELD_REGISTER_STRIDE)*state->vlenb);
    for(unsigned i=0;i<expected_start && i<REPLAY_ELEMENTS;++i){
        if(store_case){
            if(saved[i]!=input[f*cap+i]){++handler_errors;diag_error(E_SAVED,f,i,saved[i],input[f*cap+i]);}
            /* Masked-off prestart addresses can still be on the protected page. */
            if(active(i) && *(word *)field_address(i,f)!=input[f*cap+i]){++handler_errors;diag_error(E_PREFIX_MEMORY,f,i,*(word *)field_address(i,f),input[f*cap+i]);}
        }else if(saved[i]!=(active(i) ? original(field_address(i,f)):(word)0x5b)){++handler_errors;diag_error(E_SAVED,f,i,saved[i],active(i) ? original(field_address(i,f)):(word)0x5b);}
    }
    }
    restore_page();
#if TRACE_REPLAY
    text("RVV_REPLAY_RESTORED start=");num(state->vstart);text("\n");
#endif
    /* Changing completed elements detects an incorrect restart from element0. */
    for(unsigned i=0;i<expected_start && i<REPLAY_ELEMENTS;++i)for(unsigned f=0;f<REPLAY_FIELDS;++f)
        if(active(i))*(word *)field_address(i,f)=store_case ? poison(f*cap+i):(word)(original(field_address(i,f))^0x5b);
    /* Keep the saved PC, vstart and vector register data unchanged. */
#if NEGATIVE_RESTART
    state->vstart=0;
#endif
#if NEGATIVE_SKIP
    state->vstart=REPLAY_ELEMENTS;
#endif
    diag_in_handler=0;
}
struct action {
    void (*handler)(int,siginfo_t *,void *);
    unsigned long flags;
    sigset_t mask;
};
_Static_assert(sizeof(struct action)==sizeof(struct sigaction),"Kernel signal action ABI");
_Static_assert(offsetof(struct action,mask)==offsetof(struct sigaction,sa_mask),"Signal mask ABI");
void probe_main(void){
#if TRACE_REPLAY
    text("RVV_REPLAY_START\n");
#endif
    unsigned errors=0,cases=0,signal_count=0;
    cap=capacity();
    if(cap<8 || cap>CAPACITY_LIMIT){text("RVV_FAULT_REPLAY_CAPACITY_FAIL\n");quit(2);}
    struct action action={handler,SA_SIGINFO,{{0}}};
    if(call(134,SIGSEGV,(long)&action,0,sizeof(action.mask),0,0)){
        text("RVV_FAULT_REPLAY_SIGACTION_FAIL\n");quit(2);
    }
    for(unmapped=0;unmapped<2;++unmapped)for(store_case=0;store_case<2;++store_case)
    for(unsigned boundary=ZERO_STRIDE ? 0:1;boundary<=(ZERO_STRIDE ? 0:5) && boundary<REPLAY_ELEMENTS;boundary+=2)for(unsigned mode=0;mode<4;++mode)
#if STRIDED_REPLAY && !ZERO_STRIDE
    for(unsigned gap=1;gap<=3;gap+=2)
#endif
    for(unsigned split=0;split<(REPLAY_FIELDS>1 ? 2:1);++split){
        diag_trial=cases;
        volatile struct diag_record *d=&diagnostics[cases];
        d->trial=cases;d->unmapped=unmapped;d->store=store_case;d->boundary=boundary;
        d->mode=mode;d->gap=gap;d->split=split;d->phase=D_SETUP;
        unsigned prior_errors=errors;
        long address=call(222,0,8192,3,0x22,-1,0);
        if(address<0){text("RVV_FAULT_REPLAY_MMAP_FAIL\n");quit(2);}
        mapping=address;fill(mapping);fill(mapping+4096);
        unsigned accessible_fields=split ? REPLAY_FIELDS/2:0;
#if STRIDED_REPLAY
#if ZERO_STRIDE
        stride=0;
        target=mapping+4096-accessible_fields*sizeof(word);
#else
        stride=(REPLAY_FIELDS+gap)*sizeof(word);
#if NEGATIVE_STRIDE
        target=mapping+4096+boundary*stride-(REPLAY_FIELDS-accessible_fields)*sizeof(word);
        stride=-stride;
#else
        target=mapping+4096-boundary*stride-accessible_fields*sizeof(word);
#endif
#endif
#else
        target=mapping+4096-(boundary*REPLAY_FIELDS+accessible_fields)*sizeof(word);
#endif
        for(unsigned f=0;f<REPLAY_FIELDS;++f)for(unsigned i=0;i<cap;++i)
            input[f*cap+i]=(word)(101+(ZERO_STRIDE ? 0:i*13)+f*29);
        for(unsigned i=0;i<CAPACITY_LIMIT;++i){
#if INDEXED_REPLAY && REPLAY_FIELDS>1
            /* Keep the first protected segment fixed to exercise field splits. */
            unsigned slot=i<boundary ? (i+1)%boundary:i==boundary ? boundary:
                          i<REPLAY_ELEMENTS ? boundary+1+(i-boundary)%(REPLAY_ELEMENTS-boundary-1):i;
            offsets[i]=(index_word)(slot*REPLAY_FIELDS*sizeof(word));
#else
            unsigned slot=i<boundary ? (i+1)%boundary:
                          i<8 ? boundary+(i-boundary+1)%(8-boundary):i;
            offsets[i]=(index_word)(slot*sizeof(word));
#endif
        }
        for(unsigned i=0;i<CAPACITY_LIMIT*REPLAY_FIELDS+2;++i)output[i]=(word)0x5b;
        for(unsigned i=0;i<CAPACITY_LIMIT/8;++i)mask[i]=mode==0 ? 255:mode==1 ? 0xaa:mode==2 ? 0x24:0;
        expected_start=REPLAY_ELEMENTS;
        for(unsigned i=boundary;i<REPLAY_ELEMENTS;++i)if(active(i)){expected_start=i;break;}
        expected_address=element_address(expected_start);faults=0;handler_errors=0;
        d->map=mapping;d->base=target;d->expected_addr=expected_address;d->expected_start=expected_start;d->phase=D_PROTECT;
        if(call(unmapped ? 215:226,PROTECTED_PAGE,4096,0,0,0,0)){
            text("RVV_FAULT_REPLAY_PROTECT_FAIL\n");quit(2);
        }
#if TRACE_REPLAY
        text("RVV_REPLAY_TRIAL unmapped=");num(unmapped);text(" store=");num(store_case);
        text(" boundary=");num(boundary);text(" mode=");num(mode);text("\n");
#endif
        d->phase=D_HELPER;
        unsigned long status=(store_case ? replay_1:replay_0)((void *)target,input,output+1,mask,cap,
#if STRIDED_REPLAY
                                                          &stride);
#else
                                                          offsets);
#endif
        d->phase=D_RETURN;
        if(status || faults!=(expected_start<REPLAY_ELEMENTS)){
            ++errors;
            if(status)diag_error(E_RETURN,0,0,status,0);
            else diag_error(E_FAULTS,0,0,faults,expected_start<REPLAY_ELEMENTS);
        }
        errors+=handler_errors;signal_count+=faults;
        if(!faults)restore_page();
        d->phase=D_OUTPUT;
        for(unsigned f=0;f<REPLAY_FIELDS;++f)for(unsigned i=0;i<cap;++i){
            word wanted=store_case ? input[f*cap+i]:i<REPLAY_ELEMENTS && active(i) ? original(field_address(i,f)):(word)0x5b;
            if(output[f*cap+i+1]!=wanted){++errors;diag_error(E_OUTPUT,f,i,output[f*cap+i+1],wanted);}
        }
        d->phase=D_MEMORY;
        for(unsigned i=0;i<8192/sizeof(word);++i){
            uintptr_t at=mapping+i*sizeof(word);word wanted=original(at);
            unsigned slot=logical_element(at),j=slot/REPLAY_FIELDS,f=slot%REPLAY_FIELDS;
            if(store_case && j<REPLAY_ELEMENTS){
                if(active(j))wanted=faults && j<expected_start ? poison(f*cap+j):input[f*cap+j];
            }else if(!store_case && faults && j<expected_start){
                if(active(j))wanted^=0x5b;
            }
            if(((word *)mapping)[i]!=wanted){++errors;diag_error(E_MEMORY,f,i,((word *)mapping)[i],wanted);}
        }
        d->phase=D_GUARD;
        if(output[0]!=(word)0x5b || output[cap*REPLAY_FIELDS+1]!=(word)0x5b){
            ++errors;unsigned gi=output[0]!=(word)0x5b ? 0:cap*REPLAY_FIELDS+1;
            diag_error(E_GUARD,0,gi,output[gi],(word)0x5b);
        }
        d->signal_count=faults;d->handler_error_count=handler_errors;d->error_delta=errors-prior_errors;
        d->phase=D_UNMAP;
        call(215,mapping,8192,0,0,0,0);++cases;
        d->phase=D_DONE;d->complete=1;
        if(cases==DIAG_CASES)goto prefix_done;
    }
prefix_done:
    diag_emit(cases);
    text(errors ? "RVV_FAULT_REPLAY_FAIL sew=":"RVV_FAULT_REPLAY_PASS sew=");num(SEW);
    text(" cases=");num(cases);text(" signals=");num(signal_count);text(" errors=");num(errors);text("\n");quit(errors ? 1:0);
}
__asm__(".global _start\n_start:\n.option push\n.option norelax\nla gp,__global_pointer$\n.option pop\ntail probe_main\n");
