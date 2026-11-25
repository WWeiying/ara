/* Isolated NEW-gate/TEST-kernel safety prerequisite, not an OS isolation proof. */
#define _GNU_SOURCE
#include "direct_client.h"
#include <errno.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

enum test_case { UNLEASED_INFO, UNLEASED_RVV, OWNER_SYSCALLS, POST_RELEASE,
    OWNER_EXIT, NEW_OWNER, OWNED_FORK, OWNED_SIGNAL, OWNED_FAULT,
    FOREIGN_OWNER, FOREIGN_TASK, CASES };
enum tag { READY = 1, ACQUIRED, INFO_OK, YIELD_OK, RELEASED, DONE, INFO_INTENT,
    EXIT_INTENT, FORK_INTENT, SIGNAL_INTENT, FAULT_INTENT, FOREIGN_WAIT,
    DENIED_RELEASE, DENIED_ACQUIRE, UNEXPECTED_CHILD, FAILURE };
struct event { uint64_t tag, value; };
static const uint64_t info_word = UINT64_C(0x0000040000040301);
static const char *const names[CASES] = {"unleased-info", "unleased-rvv", "owner-syscalls",
    "post-release", "owner-exit", "new-owner", "owned-fork", "owned-signal",
    "owned-prot-none", "foreign-owner", "foreign-task"};
static const int signals[CASES] = {SIGILL, 0, 0, SIGILL, 0, 0,
    SIGKILL, SIGKILL, SIGKILL, 0, SIGILL};
static const unsigned plans[CASES][8] = {
    {READY, INFO_INTENT}, {READY, DONE},
    {READY, ACQUIRED, INFO_OK, YIELD_OK, RELEASED, DONE},
    {READY, ACQUIRED, RELEASED, INFO_INTENT},
    {READY, ACQUIRED, EXIT_INTENT}, {READY, ACQUIRED, RELEASED, DONE},
    {READY, ACQUIRED, FORK_INTENT}, {READY, ACQUIRED, SIGNAL_INTENT},
    {READY, ACQUIRED, FAULT_INTENT},
    {READY, ACQUIRED, FOREIGN_WAIT, INFO_OK, RELEASED, DONE},
    {READY, DENIED_RELEASE, DENIED_ACQUIRE, INFO_INTENT},
};
static const unsigned lengths[CASES] = {2, 2, 6, 4, 3, 4, 3, 3, 3, 6, 4};

static int valid_events(unsigned which, const struct event *events, unsigned count)
{
    if (which >= CASES || count != lengths[which]) return 0;
    for (unsigned i = 0; i < count; ++i) {
        if (events[i].tag != plans[which][i]) return 0;
        uint64_t wanted = 0;
        switch (events[i].tag) {
        case ACQUIRED: if (!events[i].value) return 0; continue;
        case INFO_OK: case YIELD_OK: wanted = info_word; break;
        case DENIED_RELEASE: wanted = (uint64_t)(int64_t)-EPERM; break;
        case DENIED_ACQUIRE: wanted = (uint64_t)(int64_t)-EBUSY; break;
        case SIGNAL_INTENT: wanted = SIGUSR1; break;
        default: break;
        }
        if (events[i].value != wanted) return 0;
    }
    return 1;
}

static int valid_wait(unsigned which, int status, int forced, int phases_valid)
{
    if (which >= CASES || forced || !phases_valid) return 0;
    if (!signals[which]) return status == 0 && WIFEXITED(status) && WEXITSTATUS(status) == 0;
    return status == signals[which] && WIFSIGNALED(status) &&
           WTERMSIG(status) == signals[which] && !WCOREDUMP(status);
}

#ifdef LEASE_SMOKE_HOST_TEST
/* Only this pure classification main is ever executed by the host test driver. */
int main(void)
{
    unsigned checks = 0;
    for (unsigned which = 0; which < CASES; ++which) {
        struct event events[8] = {{0}};
        for (unsigned i = 0; i < lengths[which]; ++i) {
            events[i].tag = plans[which][i];
            if (events[i].tag == ACQUIRED) events[i].value = 1;
            if (events[i].tag == INFO_OK || events[i].tag == YIELD_OK) events[i].value = info_word;
            if (events[i].tag == DENIED_RELEASE) events[i].value = (uint64_t)(int64_t)-EPERM;
            if (events[i].tag == DENIED_ACQUIRE) events[i].value = (uint64_t)(int64_t)-EBUSY;
            if (events[i].tag == SIGNAL_INTENT) events[i].value = SIGUSR1;
        }
        if (!names[which] || !valid_events(which, events, lengths[which])) return 1;
        for (unsigned i = 0; i < lengths[which]; ++i) {
            uint64_t saved = events[i].tag; events[i].tag = FAILURE;
            if (valid_events(which, events, lengths[which])) return 2;
            events[i].tag = saved;
        }
        if (valid_events(which, events, lengths[which]-1)) return 3;
        for (int status = 0; status < 65536; ++status) {
            const int wanted = status == signals[which];
            if (valid_wait(which, status, 0, 1) != wanted || valid_wait(which, status, 1, 1) ||
                valid_wait(which, status, 0, 0)) return 4;
            ++checks;
        }
        /* Missing post-acquire intent can never convert an early fault into PASS. */
        if (valid_wait(which, SIGILL, 0, 0) || valid_wait(which, SIGKILL, 0, 0)) return 5;
    }
    printf("LEASE_SMOKE_HOST_PASS cases=%u wait_checks=%u\n", CASES, checks);
    return 0;
}
#else
#if !defined(__riscv) || __riscv_xlen != 64
#error "Board smoke requires the actual GNU RV64 Linux static build"
#endif
#include <asm/unistd.h>

enum { PREPARE_MS = 30000, CASE_MS = 8000, CLEANUP_MS = 2000, MAX_EVENTS = 12 };
struct child {
    pid_t pid;
    int command[2], reply[2], status, reaped, forced, group_ready;
    struct event events[MAX_EVENTS];
    unsigned count;
};
static struct child children[CASES];

static inline long scalar(long nr, long x0, long x1, long x2, long x3, long x4, long x5)
{
    register long a0 asm("a0") = x0, a1 asm("a1") = x1, a2 asm("a2") = x2;
    register long a3 asm("a3") = x3, a4 asm("a4") = x4, a5 asm("a5") = x5;
    register long a7 asm("a7") = nr;
    asm volatile("ecall" : "+r"(a0) : "r"(a1), "r"(a2), "r"(a3), "r"(a4), "r"(a5), "r"(a7) : "memory");
    return a0;
}

static __attribute__((noreturn)) void child_exit(int code)
{
    scalar(__NR_exit_group, code, 0, 0, 0, 0, 0);
    for (;;) { }
}

static void emit(int fd, unsigned tag, uint64_t value)
{
    const struct event event = {tag, value};
    if (scalar(__NR_write, fd, (long)&event, sizeof(event), 0, 0, 0) != sizeof(event)) child_exit(90);
}

static __attribute__((noreturn)) void fail_child(int fd, long error)
{
    emit(fd, FAILURE, (uint64_t)error); child_exit(91);
}

static long fork_process(void)
{
    /* RV64 clone(SIGCHLD, sp=0) is fork, without libc atfork callbacks. */
    return scalar(__NR_clone, SIGCHLD, 0, 0, 0, 0, 0);
}

static __attribute__((noinline, noclone)) uint64_t gate_info(void)
{
    uint64_t result, index = 4;
    asm volatile(".insn r 0x5b, 4, 0, %0, %1, x0" : "=r"(result) : "r"(index) : "memory");
    return result;
}

static __attribute__((noinline)) unsigned warm_rvv(void)
{
    unsigned long result;
    asm volatile("vsetivli zero, 4, e32, m1, ta, ma\nvmv.v.i v0, 7\nvmv.x.s %0, v0"
                 : "=r"(result) : : "v0", "memory");
    return (unsigned)result;
}

static __attribute__((noinline)) void warm_f(void)
{
    asm volatile("csrwi vstart, 0\ncsrwi vcsr, 0\ncsrwi fcsr, 0\n"
                 "fmv.d.x ft0, zero\nfadd.d ft0, ft0, ft0" : : : "ft0", "memory");
}

static __attribute__((noinline)) void prefault_stack(void)
{
    volatile unsigned char stack[128 * 1024];
    for (unsigned i = 0; i < sizeof(stack); i += 4096) stack[i] = 1;
    stack[sizeof(stack)-1] = 1;
    asm volatile("" : : "r"(&stack[0]) : "memory");
}

static void command_byte(int command_fd, int reply_fd)
{
    unsigned char command = 0;
    if (scalar(__NR_read, command_fd, (long)&command, 1, 0, 0, 0) != 1 || command != 'G')
        fail_child(reply_fd, -EPIPE);
}

static void owned_case(unsigned which, int fd, int command_fd, int reply_fd, void *fault, long pid)
{
    struct ara_akv_direct_lease lease;
    long rc = ara_akv_direct_acquire(fd, &lease);
    if (rc) fail_child(reply_fd, rc);
    /* The owner must execute INFO successfully, not merely survive ACQUIRE. */
    if (gate_info() != info_word) fail_child(reply_fd, -EPROTO);
    emit(reply_fd, ACQUIRED, lease.generation);
    switch (which) {
    case OWNER_SYSCALLS:
        if (scalar(__NR_getpid, 0, 0, 0, 0, 0, 0) != pid || gate_info() != info_word)
            fail_child(reply_fd, -EPROTO);
        emit(reply_fd, INFO_OK, info_word);
        if (scalar(__NR_sched_yield, 0, 0, 0, 0, 0, 0) || gate_info() != info_word)
            fail_child(reply_fd, -EPROTO);
        emit(reply_fd, YIELD_OK, info_word);
        break;
    case OWNER_EXIT:
        emit(reply_fd, EXIT_INTENT, 0);
        child_exit(0); /* Deliberately no RELEASE: exercise exit/FD cleanup. */
    case OWNED_FORK: {
        emit(reply_fd, FORK_INTENT, 0);
        long child = fork_process();
        /* Any fork return/child is a failure, even if SIGCHLD later kills the owner. */
        emit(reply_fd, UNEXPECTED_CHILD, (uint64_t)child);
        child_exit(92);
    }
    case OWNED_SIGNAL:
        emit(reply_fd, SIGNAL_INTENT, SIGUSR1);
        scalar(__NR_kill, pid, SIGUSR1, 0, 0, 0, 0);
        fail_child(reply_fd, -EPROTO);
    case OWNED_FAULT: {
        emit(reply_fd, FAULT_INTENT, 0);
        volatile unsigned char value = *(volatile unsigned char *)fault;
        fail_child(reply_fd, value);
    }
    case FOREIGN_OWNER:
        emit(reply_fd, FOREIGN_WAIT, 0);
        /* The other task is a precreated sibling, never this owner's child. */
        command_byte(command_fd, reply_fd);
        if (gate_info() != info_word) fail_child(reply_fd, -EPROTO);
        emit(reply_fd, INFO_OK, info_word);
        break;
    default: break;
    }
    rc = ara_akv_direct_release(fd);
    if (rc) fail_child(reply_fd, rc);
    emit(reply_fd, RELEASED, 0);
    if (which == POST_RELEASE) {
        emit(reply_fd, INFO_INTENT, 0); (void)gate_info(); fail_child(reply_fd, -EPROTO);
    }
    emit(reply_fd, DONE, 0); child_exit(0);
}

static __attribute__((noreturn)) void run_child(unsigned which, int shared)
{
    int command_fd = children[which].command[0], reply_fd = children[which].reply[1];
    for (unsigned i = 0; i < CASES; ++i) {
        close(children[i].command[1]); close(children[i].reply[0]);
        if (i != which) { close(children[i].command[0]); close(children[i].reply[1]); }
    }
    if (setpgid(0, 0)) fail_child(reply_fd, -errno);
    sigset_t empty; sigemptyset(&empty);
    if (sigprocmask(SIG_SETMASK, &empty, NULL)) fail_child(reply_fd, -errno);
    const struct sigaction action = {.sa_handler = SIG_DFL};
    const int reset[] = {SIGILL, SIGUSR1, SIGSEGV, SIGBUS, SIGCHLD, SIGALRM};
    for (unsigned i = 0; i < sizeof(reset)/sizeof(reset[0]); ++i)
        if (sigaction(reset[i], &action, NULL)) fail_child(reply_fd, -errno);
    struct ara_akv_direct_info info;
    int fd = ara_akv_direct_open(&info);
    if (fd < 0) fail_child(reply_fd, fd);
    if (which == FOREIGN_OWNER || which == FOREIGN_TASK) { ara_akv_direct_close(fd); fd = shared; }
    else close(shared);
    warm_f();
    if (warm_rvv() != 7 || fflush(NULL)) fail_child(reply_fd, -EPROTO);
    const struct rlimit unlimited = {RLIM_INFINITY, RLIM_INFINITY};
    if (setrlimit(RLIMIT_MEMLOCK, &unlimited) || mlockall(MCL_CURRENT | MCL_FUTURE))
        fail_child(reply_fd, -errno);
    prefault_stack();
    void *fault = NULL;
    if (which == OWNED_FAULT) {
        fault = mmap(NULL, 4096, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        if (fault == MAP_FAILED) fail_child(reply_fd, -errno);
    }
    const long pid = scalar(__NR_getpid, 0, 0, 0, 0, 0, 0);
    emit(reply_fd, READY, 0); command_byte(command_fd, reply_fd);
    if (which == UNLEASED_RVV) {
        if (warm_rvv() != 7) fail_child(reply_fd, -EPROTO);
        emit(reply_fd, DONE, 0); child_exit(0);
    }
    if (which == FOREIGN_TASK) {
        long rc = ara_akv_direct_release(fd);
        emit(reply_fd, DENIED_RELEASE, (uint64_t)rc);
        if (rc != -EPERM) fail_child(reply_fd, rc);
        struct ara_akv_direct_lease lease;
        rc = ara_akv_direct_acquire(fd, &lease);
        emit(reply_fd, DENIED_ACQUIRE, (uint64_t)rc);
        if (rc != -EBUSY) fail_child(reply_fd, rc);
    }
    if (which == UNLEASED_INFO || which == FOREIGN_TASK) {
        emit(reply_fd, INFO_INTENT, 0); (void)gate_info(); fail_child(reply_fd, -EPROTO);
    }
    owned_case(which, fd, command_fd, reply_fd, fault, pid);
    child_exit(93);
}

static int64_t milliseconds(void)
{
    struct timespec time;
    if (clock_gettime(CLOCK_MONOTONIC, &time)) return -1;
    return (int64_t)time.tv_sec * 1000 + time.tv_nsec / 1000000;
}

static int receive(struct child *child, int64_t deadline)
{
    for (;;) {
        int64_t now = milliseconds(), left = deadline - now;
        if (now < 0 || left <= 0) return -1;
        struct pollfd pollfd = {.fd = child->reply[0], .events = POLLIN};
        int rc = poll(&pollfd, 1, (int)left);
        if (rc < 0 && errno == EINTR) continue;
        if (rc <= 0 || pollfd.revents & (POLLERR | POLLNVAL)) return -1;
        struct event event;
        ssize_t size = read(child->reply[0], &event, sizeof(event));
        if (size == 0) return 0;
        if (size != sizeof(event) || child->count == MAX_EVENTS) return -1;
        child->events[child->count++] = event;
        return event.tag == FAILURE || event.tag == UNEXPECTED_CHILD ? -1 : 1;
    }
}

static int send_go(struct child *child)
{
    const char go = 'G';
    return write(child->command[1], &go, 1) == 1 ? 0 : -1;
}

static int collect(unsigned which, int64_t deadline, uint64_t *generation)
{
    struct child *child = &children[which];
    int rc;
    while ((rc = receive(child, deadline)) > 0) { }
    if (rc < 0) return -1;
    for (;;) {
        pid_t pid = waitpid(child->pid, &child->status, WNOHANG);
        if (pid == child->pid) { child->reaped = 1; break; }
        int64_t now = milliseconds();
        if ((pid < 0 && errno != EINTR) || now < 0 || now >= deadline) return -1;
        (void)poll(NULL, 0, 1);
    }
    int phases = valid_events(which, child->events, child->count);
    int pass = valid_wait(which, child->status, child->forced, phases);
    for (unsigned i = 0; i < child->count && pass; ++i)
        if (child->events[i].tag == ACQUIRED) {
            if (child->events[i].value <= *generation) pass = 0;
            *generation = child->events[i].value;
        }
    printf("LEASE_SMOKE_WAIT case=%s pid=%ld raw=0x%04x exit=%d signal=%d core=%d forced=%d phases=%d pass=%d\n",
        names[which], (long)child->pid, child->status,
        WIFEXITED(child->status) ? WEXITSTATUS(child->status) : -1,
        WIFSIGNALED(child->status) ? WTERMSIG(child->status) : 0,
        !!WCOREDUMP(child->status), child->forced, phases, pass);
    return pass ? 0 : -1;
}

static void cleanup(void)
{
    for (unsigned i = 0; i < CASES; ++i) {
        struct child *child = &children[i];
        if (child->pid <= 0 || child->reaped) continue;
        child->forced = 1;
        if (child->group_ready) (void)kill(-child->pid, SIGKILL);
        (void)kill(child->pid, SIGKILL);
    }
    for (unsigned tick = 0; tick < CLEANUP_MS; ++tick) {
        int pending = 0;
        for (unsigned i = 0; i < CASES; ++i) {
            struct child *child = &children[i];
            if (child->pid <= 0 || child->reaped) continue;
            if (waitpid(child->pid, &child->status, WNOHANG) == child->pid) child->reaped = 1;
            else pending = 1;
        }
        if (!pending) break;
        (void)poll(NULL, 0, 1);
    }
    for (unsigned i = 0; i < CASES; ++i)
        if (children[i].forced)
            printf("LEASE_SMOKE_CLEANUP case=%s pid=%ld reaped=%d raw=0x%04x forced=1 pass=0\n",
                names[i], (long)children[i].pid, children[i].reaped, children[i].status);
}

int main(int argc, char **argv)
{
    if (argc != 2 || strcmp(argv[1], "--new-gate-lease-smoke")) {
        fprintf(stderr, "Requires isolated NEW gate + TEST kernel; safety-only.\n"); return 64;
    }
    setvbuf(stdout, NULL, _IONBF, 0); setvbuf(stderr, NULL, _IONBF, 0);
    const struct rlimit no_core = {0, 0};
    const struct sigaction normal = {.sa_handler = SIG_DFL};
    const struct sigaction ignore = {.sa_handler = SIG_IGN};
    if (setrlimit(RLIMIT_CORE, &no_core) || sigaction(SIGCHLD, &normal, NULL) ||
        sigaction(SIGPIPE, &ignore, NULL) || geteuid() || sysconf(_SC_NPROCESSORS_ONLN) != 1 ||
        getpid() == 1 || milliseconds() < 0 || prctl(69, 2, 0, 0, 0)) {
        fprintf(stderr, "LEASE_SMOKE_SETUP_FAIL root/single-CPU/vector-policy\n"); return 65;
    }
    struct ara_akv_direct_info info;
    int shared = ara_akv_direct_open(&info);
    if (shared < 0) { fprintf(stderr, "LEASE_SMOKE_SETUP_FAIL new-gate-info rc=%d\n", shared); return 66; }
    printf("LEASE_SMOKE_PREFLIGHT abi=%u features=%u signature=%016llx cpus=%u children=%u\n",
        info.abi, info.features, (unsigned long long)info.gate_signature, info.online_cpus, CASES);
    for (unsigned i = 0; i < CASES; ++i)
        if (pipe(children[i].command) || pipe(children[i].reply)) {
            ara_akv_direct_close(shared); return 67;
        }
    /* Create every sibling before dispatching ANY lease acquisition. */
    for (unsigned i = 0; i < CASES; ++i) {
        long pid = fork_process();
        if (pid == 0) run_child(i, shared);
        if (pid < 0) { cleanup(); ara_akv_direct_close(shared); return 68; }
        children[i].pid = (pid_t)pid;
    }
    ara_akv_direct_close(shared);
    for (unsigned i = 0; i < CASES; ++i) { close(children[i].command[0]); close(children[i].reply[1]); }
    unsigned passed = 0;
    uint64_t generation = 0;
    int failed = 0;
    int64_t deadline = milliseconds() + PREPARE_MS;
    for (unsigned i = 0; i < CASES; ++i) {
        struct child *child = &children[i];
        if (receive(child, deadline) != 1 || child->count != 1 || child->events[0].tag != READY ||
            getpgid(child->pid) != child->pid) { failed = 1; break; }
        child->group_ready = 1;
    }
    for (unsigned i = 0; i < FOREIGN_OWNER && !failed; ++i) {
        if (send_go(&children[i]) || collect(i, milliseconds()+CASE_MS, &generation)) failed = 1;
        else ++passed;
    }
    if (!failed) {
        struct child *owner = &children[FOREIGN_OWNER];
        deadline = milliseconds() + CASE_MS;
        if (send_go(owner)) failed = 1;
        while (!failed && owner->events[owner->count-1].tag != FOREIGN_WAIT)
            if (receive(owner, deadline) != 1) failed = 1;
        if (!failed && (send_go(&children[FOREIGN_TASK]) ||
            collect(FOREIGN_TASK, deadline, &generation))) failed = 1;
        if (!failed) ++passed;
        if (!failed) {
            pid_t state = waitpid(owner->pid, &owner->status, WNOHANG);
            if (state == owner->pid) owner->reaped = 1;
            if (state != 0 || send_go(owner) || collect(FOREIGN_OWNER, deadline, &generation)) failed = 1;
        }
        if (!failed) ++passed;
    }
    cleanup();
    printf("LEASE_SMOKE_DONE passed=%u total=%u errors=%d scope=bounded-safety-not-OS-proof\n",
        passed, CASES, failed);
    return failed || passed != CASES;
}
#endif
