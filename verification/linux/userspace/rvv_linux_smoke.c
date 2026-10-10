#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <sched.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/auxv.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <ucontext.h>
#include <unistd.h>

extern size_t rvv_vlenb(void);
extern void rvv_add_u32(const uint32_t *, const uint32_t *, uint32_t *, size_t);
extern void rvv_max_f32(const uint32_t *, const uint32_t *, uint32_t *, size_t);
extern void rvv_clobber_state(const uint8_t *);
extern uint64_t rvv_context_probe(const uint8_t *, uint8_t *, uint64_t *,
                                 unsigned, volatile void *, size_t);
extern const char rvv_illegal_site[], rvv_illegal_resume[], rvv_fault_site[];
extern int custom_caps_probe(void);

static volatile sig_atomic_t signal_count, fault_count, illegal_count;
static uint8_t *handler_pattern;
static void *fault_page;
static size_t page_size;
static const uint64_t parent_csrs[] = {9, 9, 3, 3}; // e16/m2/tu/mu
static const uint64_t child_csrs[] = {11, 1, 1, 5}; // e8/m2/tu/mu
static const uint64_t fault_sentinel = UINT64_C(0x13579bdf2468ace0);

static void die(const char *what) {
    fprintf(stderr, "[LINUX_RVV] FAIL %s errno=%d\n", what, errno);
    exit(1);
}

static void handler(int sig, siginfo_t *info, void *context) {
    ucontext_t *uc = context;
    if (sig == SIGALRM) {
        ++signal_count;
    } else if (sig == SIGSEGV) {
        if (info->si_addr != fault_page || info->si_code != SEGV_ACCERR ||
            uc->uc_mcontext.__gregs[REG_PC] != (uintptr_t)rvv_fault_site ||
            syscall(SYS_mprotect, fault_page, page_size, PROT_READ | PROT_WRITE))
            _exit(121);
        *(volatile uint64_t *)fault_page = fault_sentinel;
        ++fault_count;
    } else if (sig == SIGILL) {
        if (uc->uc_mcontext.__gregs[REG_PC] != (uintptr_t)rvv_illegal_site)
            _exit(122);
        uc->uc_mcontext.__gregs[REG_PC] = (uintptr_t)rvv_illegal_resume;
        ++illegal_count;
    } else {
        _exit(123);
    }
    // Deliberately overwrite every vector register; sigreturn must restore the
    // interrupted state. The handler's own scalar calls need not preserve it.
    rvv_clobber_state(handler_pattern);
}

static void fill(uint8_t *p, size_t n, unsigned seed) {
    for (size_t i = 0; i < n; ++i)
        p[i] = (uint8_t)(seed + i * 29 + (i >> 4));
}

static void poison_snapshot(const uint8_t *expected, uint8_t *actual, size_t n,
                            uint64_t *csr) {
    for (size_t i = 0; i < n; ++i) actual[i] = expected[i] ^ 0xff;
    for (size_t i = 0; i < 4; ++i) csr[i] = UINT64_MAX;
}

static void check_state(const char *name, const uint8_t *expected,
                        const uint8_t *actual, size_t n, const uint64_t *csr,
                        const uint64_t *wanted) {
    for (size_t i = 0; i < n; ++i) {
        if (actual[i] != expected[i]) {
            fprintf(stderr, "[LINUX_RVV] FAIL %s byte=%zu expected=%02x actual=%02x\n",
                    name, i, expected[i], actual[i]);
            exit(1);
        }
    }
    for (size_t i = 0; i < 4; ++i) {
        if (csr[i] != wanted[i]) {
            fprintf(stderr, "[LINUX_RVV] FAIL %s csr=%zu expected=%" PRIu64
                    " actual=%" PRIu64 "\n", name, i, wanted[i], csr[i]);
            exit(1);
        }
    }
    printf("[LINUX_RVV] PASS %s bytes=%zu vl=%" PRIu64
           " vtype=%" PRIu64 " vstart=%" PRIu64 " vcsr=%" PRIu64 "\n",
           name, n, csr[0], csr[1], csr[2], csr[3]);
}

int main(void) {
    setvbuf(stdout, NULL, _IONBF, 0);
    if (!(getauxval(AT_HWCAP) & (1UL << ('V' - 'A')))) die("HWCAP V absent");
    const size_t vlenb = rvv_vlenb();
    if (vlenb < 16 || vlenb > 8192 || (vlenb & (vlenb - 1))) die("invalid VLENB");
    const size_t bytes = 32 * vlenb;
    uint8_t *expected = malloc(bytes), *actual = malloc(bytes);
    handler_pattern = malloc(bytes);
    if (!expected || !actual || !handler_pattern) die("malloc");
    fill(expected, bytes, 17);
    fill(handler_pattern, bytes, 203);
    printf("[LINUX_RVV] INFO vlenb=%zu state_bytes=%zu\n", vlenb, bytes);

    size_t count = 3 * (vlenb / 4) + 5;
    uint32_t *x = malloc(count * sizeof(*x)), *y = malloc(count * sizeof(*y));
    uint32_t *z = calloc(count + 2, sizeof(*z));
    if (!x || !y || !z) die("arithmetic buffers");
    for (size_t i = 0; i < count; ++i) {
        x[i] = (uint32_t)i * 7919;
        y[i] = ((uint32_t)i * 3571) ^ UINT32_C(0xa5a50f0f);
    }
    z[0] = z[count + 1] = 0x5a55a55a;
    rvv_add_u32(x, y, z + 1, count);
    for (size_t i = 0; i < count; ++i)
        if (z[i + 1] != (uint32_t)(x[i] + y[i])) die("VLA arithmetic/load/store");
    if (z[0] != 0x5a55a55a || z[count + 1] != 0x5a55a55a) die("store guard");
    printf("[LINUX_RVV] PASS arithmetic_load_store elements=%zu\n", count);

    const uint32_t data[] = {0xc1700000, 0x41700000, 0x3f800000, 0xc0000000};
    const uint32_t seed = 0xff800000;
    uint32_t result = 0;
    rvv_max_f32(data, &seed, &result, 4);
    if (result != 0x41700000) die("VFREDMAX VL4");
    rvv_max_f32(data, &seed, &result, 1);
    if (result != 0xc1700000) die("VFREDMAX VL1");
    puts("[LINUX_RVV] PASS vfredmax_boundary");

    // Both processes run on the same CPU with distinct live patterns. Their
    // handshake is entirely userspace, so syscall clobber rules do not apply.
    cpu_set_t available, affinity;
    if (sched_getaffinity(0, sizeof(available), &available)) die("getaffinity");
    int cpu;
    for (cpu = 0; cpu < CPU_SETSIZE && !CPU_ISSET(cpu, &available); ++cpu) {}
    if (cpu == CPU_SETSIZE) die("no CPU");
    CPU_ZERO(&affinity); CPU_SET(cpu, &affinity);
    if (sched_setaffinity(0, sizeof(affinity), &affinity)) die("setaffinity");
    volatile int *turn = mmap(NULL, 4096, PROT_READ | PROT_WRITE,
                              MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    if (turn == MAP_FAILED) die("shared turn");
    *turn = 0;
    pid_t child = fork();
    if (child < 0) die("fork");
    uint64_t csr[4];
    struct rusage before, after;
    if (getrusage(RUSAGE_SELF, &before)) die("rusage before");
    alarm(30); // bounded deadlock detector; SIGALRM handler installed later
    if (child == 0) fill(expected, bytes, 91);
    poison_snapshot(expected, actual, bytes, csr);
    rvv_context_probe(expected, actual, csr, child == 0 ? 1 : 0, turn, 32);
    alarm(0);
    if (getrusage(RUSAGE_SELF, &after)) die("rusage after");
    if (after.ru_nivcsw <= before.ru_nivcsw) die("no observed preemption");
    check_state(child == 0 ? "preempt_child" : "preempt_parent", expected, actual, bytes, csr,
                child == 0 ? child_csrs : parent_csrs);
    printf("[LINUX_RVV] INFO involuntary_switches=%ld cpu=%d\n",
           after.ru_nivcsw - before.ru_nivcsw, cpu);
    if (child == 0) _exit(0);
    int status;
    if (waitpid(child, &status, 0) != child || !WIFEXITED(status) || WEXITSTATUS(status))
        die("child status");

    struct sigaction action = {.sa_sigaction = handler, .sa_flags = SA_SIGINFO};
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGALRM, &action, NULL) || sigaction(SIGSEGV, &action, NULL) ||
        sigaction(SIGILL, &action, NULL)) die("sigaction");
    struct itimerval timer = {.it_interval = {0, 10000}, .it_value = {0, 10000}};
    poison_snapshot(expected, actual, bytes, csr);
    if (setitimer(ITIMER_REAL, &timer, NULL)) die("setitimer");
    rvv_context_probe(expected, actual, csr, 2, &signal_count, 0);
    memset(&timer, 0, sizeof(timer));
    if (setitimer(ITIMER_REAL, &timer, NULL)) die("stop timer");
    if (!signal_count) die("no signal");
    check_state("signal_return", expected, actual, bytes, csr, parent_csrs);

    page_size = (size_t)sysconf(_SC_PAGESIZE);
    fault_page = mmap(NULL, page_size, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (fault_page == MAP_FAILED) die("fault mmap");
    poison_snapshot(expected, actual, bytes, csr);
    uint64_t fault_value = rvv_context_probe(expected, actual, csr, 3, fault_page, 0);
    if (fault_count != 1) die("fault count");
    if (fault_value != fault_sentinel) die("faulting load was not retried correctly");
    check_state("scalar_fault_return", expected, actual, bytes, csr, parent_csrs);

    poison_snapshot(expected, actual, bytes, csr);
    rvv_context_probe(expected, actual, csr, 4, NULL, 0);
    if (illegal_count != 1) die("illegal count");
    check_state("illegal_instruction_return", expected, actual, bytes, csr, parent_csrs);
    puts("RVV fallback userspace PASS");
    puts("RVV context switch and fault return PASS");
    if (custom_caps_probe()) die("custom capability probe");
    return 0;
}
