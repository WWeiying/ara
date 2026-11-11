/* Host policy fixtures only. No vector/FP arithmetic or native execution claim. */
#define STAGE5_PROVIDER_HOST_TEST 1
#ifndef __NR_riscv_hwprobe
#define __NR_riscv_hwprobe 258
#endif
#include "provider.c"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static unsigned task_count=1, aux_ok=1, probe_ok=1, current_on=1;
static unsigned long affinity=1;
static size_t aux_at, maps_at; static int dents_done;
static unsigned syscalls, reader_calls, restores, clobber_syscalls;
static uintptr_t host_thread=1;
static akv_platform_thread_state_v1 hw={128,0,8,5};
uintptr_t stage5_host_thread(void) { return host_thread; }
void stage5_host_restore(const akv_platform_thread_state_v1 *saved) { ++restores; hw=*saved; }
static const char *maps="1000-2000 rw-p 00000000 00:00 0 [heap]\n2000-3000 rw-p 00000000 00:00 0 [heap]\n";
long stage5_host_syscall(long nr,long a,long b,long c,long d,long e,long f) {
    (void)d;(void)e;(void)f;
    ++syscalls;
    if(clobber_syscalls) { hw.vstart=0;hw.vcsr=0;hw.fcsr=0; }
    if(nr==__NR_getpid || nr==__NR_gettid)return 42;
    if(nr==__NR_prctl)return current_on?PR_RISCV_V_VSTATE_CTRL_ON:PR_RISCV_V_VSTATE_CTRL_OFF;
    if(nr==__NR_riscv_hwprobe){struct riscv_hwprobe *p=(void*)a;p->value=probe_ok?
        RISCV_HWPROBE_IMA_FD|RISCV_HWPROBE_IMA_V|RISCV_HWPROBE_EXT_ZFH|RISCV_HWPROBE_EXT_ZVFH:0;return 0;}
    if(nr==__NR_openat){
        if(same((void*)b,"/proc/self/auxv")){aux_at=0;return 10;}
        if(same((void*)b,"/proc/self/task")){dents_done=0;return 11;}
        if(same((void*)b,"/proc/self/maps")){maps_at=0;return 12;}
        return -2;
    }
    if(nr==__NR_close)return 0;
    if(nr==__NR_read && a==10){
        uintptr_t data[]={AT_HWCAP,aux_ok?((1UL<<('F'-'A'))|(1UL<<('D'-'A'))|(1UL<<('V'-'A'))):0,AT_NULL,0};
        size_t n=sizeof(data)-aux_at;if(n>(size_t)c)n=c;
        memcpy((void*)b,(char*)data+aux_at,n);aux_at+=n;return n;
    }
    if(nr==__NR_read && a==12){size_t n=strlen(maps)-maps_at;if(n>(size_t)c)n=c;
        memcpy((void*)b,maps+maps_at,n);maps_at+=n;return n;}
    if(nr==__NR_getdents64){
        if(dents_done++)return 0;
        unsigned count=task_count+2;assert(count*24<=(unsigned)c);memset((void*)b,0,count*24);
        for(unsigned i=0;i<count;++i){char *p=(char*)b+i*24;p[16]=24;strcpy(p+19,i==0?".":i==1?"..":i==2?"42":"43");}
        return count*24;
    }
    if(nr==__NR_sched_getaffinity){*(unsigned long*)c=affinity;return sizeof(affinity);}
    assert(!"unexpected host fixture syscall");return -1;
}
akv_platform_result_t akv_resident_platform_read_state_v1(void *context,akv_platform_thread_state_v1 *out){
    (void)context; ++reader_calls;
    if(hw.vstart) return AKV_PLATFORM_BAD_VSTART;
    *out=hw; return AKV_PLATFORM_READY;
}
int main(void){
    akv_platform_span_v1 span={(void*)0x1800,0x1000,1};
    akv_platform_request_v1 r={1,sizeof(r),1,1,1,1,1,0,&span,1};
    assert(ram_spans(&r));assert(one_thread());
    task_count=2;assert(!one_thread());task_count=1;
    affinity=3;assert(!one_thread());affinity=1;
    maps="1000-2000 rw-p 00000000 00:00 0 [heap]\n2100-3000 rw-p 00000000 00:00 0 [heap]\n";assert(!ram_spans(&r));
    maps="1000-3000 r--p 00000000 00:00 0 [heap]\n";assert(!ram_spans(&r));span.writable=0;assert(ram_spans(&r));
    maps="1000-3000 rw-p 00000000 00:00 0 /dev/mem\n";assert(!ram_spans(&r));
    maps="1000-3000 r--p 00000000 00:00 0 [vvar]\n";assert(!ram_spans(&r));
    maps="1000-3000 rw-p 00000000 00:00 0 [heap]\n";
    span.bytes=UINTPTR_MAX;assert(!ram_spans(&r));span.bytes=0x1000;
    r.workers=2;assert(!ram_spans(&r));r.workers=1;
    r.span_count=33;assert(!ram_spans(&r));r.span_count=1;
#if STAGE5_PROVIDER_ENABLED
    unsigned calls=syscalls, reads=reader_calls;
    assert(state(NULL,(void*)1)==AKV_PLATFORM_KEEP_NATIVE && syscalls==calls && reader_calls==reads);
    assert(stage5_provider_setup_v2()==1);
    assert(os_ready());probe_ok=0;assert(!os_ready());probe_ok=1;
    aux_ok=0;assert(!os_ready());aux_ok=1;current_on=0;assert(!os_ready());current_on=1;
    assert(akv_resident_platform_current_v1()==&provider && ggml_akv_legacy_current_v1()==&legacy);
    hw.vstart=1;calls=syscalls;unsigned saves=restores;
    assert(state(NULL,(void*)1)==AKV_PLATFORM_BAD_VSTART);
    assert(!acquire(NULL,(void*)1) && syscalls==calls && restores==saves && hw.vstart==1);
    hw.vstart=0;hw.vcsr=6;hw.fcsr=104;clobber_syscalls=1;
    uintptr_t cookie=acquire(NULL,&r);assert(cookie && hw.vcsr==6 && hw.fcsr==104 && !hw.vstart);
    assert(!acquire(NULL,&r));
    hw.vstart=7;hw.vcsr=7;hw.fcsr=65;calls=syscalls;saves=restores;
    release(NULL,cookie);
    assert(!lease && syscalls==calls && restores==saves && hw.vstart==7 && hw.vcsr==7 && hw.fcsr==65);
    hw.vstart=0;hw.vcsr=5;hw.fcsr=9;
    host_thread=2;calls=syscalls;reads=reader_calls;
    assert(state(NULL,(void*)1)==AKV_PLATFORM_KEEP_NATIVE && !acquire(NULL,(void*)1));
    assert(syscalls==calls && reader_calls==reads);host_thread=1;
    task_count=2;assert(!acquire(NULL,&r) && !lease && hw.vcsr==5 && hw.fcsr==9);task_count=1;
    maps="1000-3000 rw-p 00000000 00:00 0 /dev/mem\n";
    assert(!acquire(NULL,&r) && !lease && hw.vcsr==5 && hw.fcsr==9);
    clobber_syscalls=0;current_on=0;
    assert(!stage5_provider_setup_v2());calls=syscalls;reads=reader_calls;
    assert(state(NULL,(void*)1)==AKV_PLATFORM_KEEP_NATIVE && reader_calls==reads && syscalls==calls);
#else
    assert(!os_ready() && !akv_resident_platform_current_v1() && !ggml_akv_legacy_current_v1());
    assert(!acquire(NULL,&r));
#endif
    puts("PROVIDER_V2_HOST_POLICY_AND_CSR_GUARD_PASS_NOT_NATIVE");return 0;
}
