#define DIAG_CASES 13
enum { D_SETUP=1,D_PROTECT,D_HELPER,D_RETURN,D_OUTPUT,D_MEMORY,D_GUARD,D_UNMAP,D_DONE };
enum { E_SIGNAL=1,E_ADDRESS,E_CODE,E_PC,E_VSTART,E_VL,E_VTYPE,
       E_SAVED,E_PREFIX_MEMORY,E_RETURN,E_FAULTS,E_OUTPUT,E_MEMORY,E_GUARD };
struct diag_record {
    unsigned trial,unmapped,store,boundary,mode,gap,split,phase,complete;
    unsigned signal_seen,signal_phase,frame_found,frame_valid;
    long sig,si_code;
    uintptr_t pc,signal_address,context,map,base,expected_addr;
    unsigned long saved_vl,saved_vtype,saved_vstart,saved_vlenb;
    unsigned expected_start,signal_count,error_delta,handler_error_count;
    unsigned check,check_phase,field,index;
    uint64_t actual,expected;
    const char *fatal_message;
};
static volatile struct diag_record diagnostics[DIAG_CASES];
static volatile unsigned diag_trial,diag_in_handler;
static void text(const char *s);
static void num(uint64_t n);
static void diag_error(unsigned check,unsigned field,unsigned index,uint64_t actual,uint64_t expected){
    if(diag_trial>=DIAG_CASES)return;
    volatile struct diag_record *d=&diagnostics[diag_trial];
    if(d->check)return;
    d->check_phase=d->phase;d->field=field;d->index=index;
    d->actual=actual;d->expected=expected;d->check=check;
}
static void diag_signal(int sig,const siginfo_t *info,const struct ucontext *uc){
    if(diag_trial>=DIAG_CASES)return;
    volatile struct diag_record *d=&diagnostics[diag_trial];
    if(d->signal_seen)return;
    d->sig=sig;d->si_code=info->si_code;d->signal_address=(uintptr_t)info->si_addr;
    d->pc=uc->uc_mcontext.sc_regs.pc;d->context=(uintptr_t)uc;
    d->signal_phase=d->phase;d->signal_seen=1;
}
static void diag_state(const struct __riscv_v_ext_state *state){
    if(diag_trial>=DIAG_CASES || !state)return;
    volatile struct diag_record *d=&diagnostics[diag_trial];
    if(d->frame_found)return;
    d->saved_vl=state->vl;d->saved_vtype=state->vtype;
    d->saved_vstart=state->vstart;d->saved_vlenb=state->vlenb;d->frame_found=1;
}
static void diag_hex(uint64_t v){
    char s[19];s[0]='0';s[1]='x';s[18]=0;
    for(unsigned i=0;i<16;++i)s[17-i]="0123456789abcdef"[(v>>(4*i))&15];
    text(s);
}
#define DN(key,value) do{text(" " key "=");num(value);}while(0)
#define DX(key,value) do{text(" " key "=");diag_hex(value);}while(0)
static void diag_emit(unsigned count){
    for(unsigned i=0;i<count && i<DIAG_CASES;++i){
        const volatile struct diag_record *d=&diagnostics[i];
        text("NF8_LINUX_DIAG");DN("trial",d->trial);DN("unmapped",d->unmapped);
        DN("store",d->store);DN("boundary",d->boundary);DN("mode",d->mode);
        DN("gap",d->gap);DN("split",d->split);DN("phase",d->phase);DN("complete",d->complete);
        DN("signal_seen",d->signal_seen);DN("signal_phase",d->signal_phase);DN("sig",d->sig);
        DX("si_code",(uint64_t)d->si_code);DX("pc",d->pc);DX("si_addr",d->signal_address);
        DX("context",d->context);DX("mapping",d->map);DX("target",d->base);DX("expected_addr",d->expected_addr);
        DN("frame_found",d->frame_found);DN("frame_valid",d->frame_valid);
        DN("vl",d->saved_vl);DX("vtype",d->saved_vtype);DN("vstart",d->saved_vstart);DN("vlenb",d->saved_vlenb);
        DN("expected_start",d->expected_start);DN("signals",d->signal_count);DN("error_delta",d->error_delta);
        DN("handler_errors",d->handler_error_count);DN("check",d->check);DN("check_phase",d->check_phase);
        DN("field",d->field);DN("index",d->index);DX("actual",d->actual);DX("expected",d->expected);
        if(d->fatal_message){text(" fatal=");text(d->fatal_message);}text("\n");
    }
}
#undef DN
#undef DX
