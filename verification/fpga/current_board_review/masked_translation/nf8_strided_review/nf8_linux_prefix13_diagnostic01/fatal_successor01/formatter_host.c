#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* Native formatter-only fixture, not a Linux signal-frame emulation. */
typedef struct { long si_code; void *si_addr; } siginfo_t;
struct ucontext { struct { struct { uintptr_t pc; } sc_regs; } uc_mcontext; };
struct __riscv_v_ext_state { unsigned long vl,vtype,vstart,vlenb; };
#include "diagnostic.h"
static unsigned writes;
static long write_result;
static char captured[1025];
static void text(const char *s){(void)s;assert(0);}
static void num(uint64_t n){(void)n;assert(0);}
static long call(long n,long x,long y,long z,long u,long v,long w){
    assert(n==64 && x==1 && u==0 && v==0 && w==0);
    assert(z>0 && z<=1024);++writes;
    memcpy(captured,(const void *)y,(size_t)z);captured[z]=0;
    assert(captured[z-1]=='\n');return write_result;
}
int main(void){
    diag_trial=12;
    diagnostics[12].pc=UINTPTR_MAX;
    diagnostics[12].context=1;
    diagnostics[12].signal_address=UINTPTR_MAX;
    diagnostics[12].fatal_message=(const char *)1;
    diagnostics[12].si_code=-1;
    diagnostics[12].actual=UINT64_MAX;
    diagnostics[12].expected=0x5b;
    diagnostics[12].phase=D_HELPER;
    diagnostics[12].signal_seen=1;
    for(unsigned i=0;i<3;++i){
        writes=0;write_result=i==0 ? 1024:i==1 ? 1:-1;
        diag_fatal_emit(2,2,1);
        assert(writes==1);
        assert(strstr(captured,"NF8_LINUX_FATAL exit=0x0000000000000002"));
        assert(strstr(captured,"trial=0x000000000000000c"));
        assert(strstr(captured,"complete=0x0000000000000000"));
        assert(strstr(captured,"pc=0xffffffffffffffff"));
        assert(strstr(captured,"context=0x0000000000000001"));
        assert(strstr(captured,"actual=0xffffffffffffffff"));
        assert(strstr(captured,"expected=0x000000000000005b"));
    }
    unsigned full_length=diag_fatal_length;
    diag_trial=13;writes=0;diag_fatal_emit(2,1,0);
    assert(writes==1 && strstr(captured,"trial=0x000000000000000d"));
    assert(!strstr(captured,"context="));
    printf("FORMATTER_HOST_PASS scenarios=4 full_record_bytes=%u max=1024 single_write_no_retry=1\n",full_length);
    return 0;
}
