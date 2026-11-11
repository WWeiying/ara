#define _GNU_SOURCE
#include <asm/hwprobe.h>
#include <linux/prctl.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/auxv.h>
#include <sys/prctl.h>
#include <sys/reboot.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

struct sample { uintptr_t before[5], after[5], pid, restored[5]; };
_Static_assert(sizeof(struct sample)==128, "assembly layout");
extern void stage5_csr_syscall_probe(uintptr_t,uintptr_t,uintptr_t,struct sample *,unsigned);

static int probe(void) {
    const unsigned long hw=getauxval(AT_HWCAP), mask=(1UL<<('F'-'A'))|(1UL<<('D'-'A'))|(1UL<<('V'-'A'));
    struct riscv_hwprobe ext={RISCV_HWPROBE_KEY_IMA_EXT_0,0};
    const long policy=prctl(PR_RISCV_V_GET_CONTROL,0,0,0,0);
    if((hw&mask)!=mask || policy<0 || (policy&PR_RISCV_V_VSTATE_CTRL_CUR_MASK)!=PR_RISCV_V_VSTATE_CTRL_ON ||
       syscall(__NR_riscv_hwprobe,&ext,1,0,0,0) || ext.key!=RISCV_HWPROBE_KEY_IMA_EXT_0 ||
       (ext.value&(RISCV_HWPROBE_IMA_FD|RISCV_HWPROBE_IMA_V))!=(RISCV_HWPROBE_IMA_FD|RISCV_HWPROBE_IMA_V)) return 2;
    printf("CSR_PROBE_OS hwcap=%lu policy=%ld extensions=%lu\n",hw,policy,(unsigned long)ext.value);
    const uintptr_t starts[]={0,1,7}, vcs[]={5,6,7}, fcs[]={9,104,65};
    for(unsigned i=0;i<3;++i) for(unsigned issue=0;issue<2;++issue) {
        struct sample s;
        // Known C ABI state before the assembly-only measured interval.
        asm volatile("csrwi vstart,0;csrwi vcsr,3;csrwi fcsr,8" ::: "memory");
        stage5_csr_syscall_probe(starts[i],vcs[i],fcs[i],&s,issue);
        printf("CSR_SYSCALL_SAMPLE case=%u syscall=%u",i,issue);
        for(unsigned j=0;j<5;++j) printf(" before%u=%lu",j,(unsigned long)s.before[j]);
        for(unsigned j=0;j<5;++j) printf(" after%u=%lu",j,(unsigned long)s.after[j]);
        printf(" pid=%lu",(unsigned long)s.pid);
        for(unsigned j=0;j<5;++j) printf(" restored%u=%lu",j,(unsigned long)s.restored[j]);
        puts("");
        if(s.before[0]!=starts[i] || s.before[1]!=vcs[i] || s.before[2]!=fcs[i] ||
           s.before[3]!=13 || s.before[4]!=200 || s.restored[0] || s.restored[1]!=3 || s.restored[2]!=8 ||
           (issue && s.pid<2) || (!issue && s.pid)) return 3;
        if(!issue) for(unsigned j=0;j<5;++j) if(s.before[j]!=s.after[j]) return 4;
    }
    puts("CSR_PROBE_COMPLETE samples=6 native_akv=0 model=0");
    return 0;
}

int main(void) {
    setvbuf(stdout,NULL,_IONBF,0); setvbuf(stderr,NULL,_IONBF,0);
    if(getpid()!=1) return 9;
    pid_t child=fork(); int result=127;
    if(!child) _exit(probe());
    int status;
    if(child>0 && waitpid(child,&status,0)==child && WIFEXITED(status)) result=WEXITSTATUS(status);
    printf("CSR_PROBE_CHILD_EXIT=%d\n",result);
    sync(); reboot(RB_POWER_OFF);
    for(;;) pause();
}
