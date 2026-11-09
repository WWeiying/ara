#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/resource.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

/* Standalone diagnostic: no model, custom instruction, perf permission change,
 * device access, or reboot. A forbidden CSR faults only the child process. */
static uint64_t ns(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) { perror("clock_gettime"); _exit(2); }
    return (uint64_t)t.tv_sec*UINT64_C(1000000000)+(uint64_t)t.tv_nsec;
}

#if defined(__riscv) && __riscv_xlen == 64
static uint64_t ticks(void) {
    uint64_t value;
    __asm__ volatile("rdtime %0" : "=r"(value) : : "memory");
    return value;
}

static int measure(void) {
    volatile uint64_t sink=0;
    uint64_t begin=ns();
    for (unsigned i=0;i<64;++i) sink=ns();
    uint64_t clock_elapsed=ns()-begin;
    begin=ns();
    for (unsigned i=0;i<4096;++i) sink=ticks();
    uint64_t csr_elapsed=ns()-begin;
    printf("{\"kind\":\"clock_cost_observation\",\"clock_reads\":64,"
           "\"clock_loop_ns\":%" PRIu64 ",\"rdtime_reads\":4096,"
           "\"rdtime_loop_ns\":%" PRIu64 "}\n",clock_elapsed,csr_elapsed);
    for (unsigned i=0;i<3;++i) {
        uint64_t n0=ns(), t0=ticks();
        struct timespec delay={.tv_sec=0,.tv_nsec=20000000};
        while (nanosleep(&delay,&delay)) if (errno!=EINTR) return 3;
        uint64_t t1=ticks(), n1=ns();
        if (t1<=t0 || n1<=n0) return 4;
        printf("{\"kind\":\"timebase_observation\",\"sample\":%u,"
               "\"elapsed_ns\":%" PRIu64 ",\"elapsed_ticks\":%" PRIu64 "}\n",
               i,n1-n0,t1-t0);
    }
    (void)sink;
    puts("{\"state\":\"RDTIME_READABLE_NOT_YET_CALIBRATED\","
         "\"hardware_cycles_measured\":false}");
    return 0;
}
#endif

int main(void) {
    struct rlimit limit={0,0};
    if (setrlimit(RLIMIT_CORE,&limit)) { perror("setrlimit"); return 2; }
#if defined(__riscv) && __riscv_xlen == 64
    if (fflush(NULL)) return 2;
    pid_t child=fork();
    if (child<0) { perror("fork"); return 2; }
    if (!child) {
        int rc=measure();
        if (fflush(NULL)) rc=2;
        _exit(rc);
    }
    int status;
    if (waitpid(child,&status,0)!=child) { perror("waitpid"); return 2; }
    if (WIFSIGNALED(status)) {
        printf("{\"state\":\"UNSUPPORTED_OR_CHILD_FAULT\",\"signal\":%d}\n",WTERMSIG(status));
        return 1;
    }
    if (!WIFEXITED(status)) return 2;
    return WEXITSTATUS(status);
#else
    (void)ns;
    puts("{\"state\":\"UNSUPPORTED_HOST_ARCHITECTURE\"}");
    return 1;
#endif
}
