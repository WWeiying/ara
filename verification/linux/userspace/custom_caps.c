#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <inttypes.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static uint64_t query_capability(unsigned index, int akv) {
    register uint64_t a0 __asm__("a0") = index;

    /* Reestablish vector state immediately before each scalar-only query. */
    if (akv) {
        __asm__ volatile(
            ".option push\n"
            ".option arch, +v\n"
            "vsetvli t0, zero, e8, m1, ta, ma\n"
            ".insn r 0x5b, 4, 0, a0, a0, zero\n"
            ".option pop\n"
            : "+r"(a0) : : "t0", "memory");
    } else {
        __asm__ volatile(
            ".option push\n"
            ".option arch, +v\n"
            "vsetvli t0, zero, e8, m1, ta, ma\n"
            ".insn r 0x5b, 1, 0, a0, a0, zero\n"
            ".option pop\n"
            : "+r"(a0) : : "t0", "memory");
    }
    return a0;
}

static void probe_child(int fd, int akv, size_t count) {
    const int signals[] = {SIGILL, SIGALRM, SIGSEGV, SIGBUS, SIGPIPE};
    struct sigaction action = {.sa_handler = SIG_DFL};
    sigset_t mask;
    const struct rlimit no_core = {0, 0};

    if (sigemptyset(&action.sa_mask) || sigemptyset(&mask)) _exit(1);
    for (size_t i = 0; i < sizeof(signals) / sizeof(signals[0]); ++i)
        if (sigaction(signals[i], &action, NULL)) _exit(1);
    if (sigprocmask(SIG_SETMASK, &mask, NULL) ||
        setrlimit(RLIMIT_CORE, &no_core)) _exit(1);
    alarm(5);

    uint64_t words[4];
    for (size_t i = 0; i < count; ++i)
        words[i] = query_capability((unsigned)i, akv);

    const size_t bytes = count * sizeof(words[0]);
    ssize_t written;
    do {
        written = write(fd, words, bytes);
    } while (written < 0 && errno == EINTR);
    _exit(written == (ssize_t)bytes ? 0 : 1);
}

static int wait_bounded(pid_t child, int *status) {
    struct timespec deadline, now;
    const struct timespec pause = {.tv_sec = 0, .tv_nsec = 10000000};

    if (clock_gettime(CLOCK_MONOTONIC, &deadline)) return -1;
    deadline.tv_sec += 6;
    for (;;) {
        pid_t waited = waitpid(child, status, WNOHANG);
        if (waited == child) return 0;
        if (waited < 0 && errno != EINTR) return -1;
        if (clock_gettime(CLOCK_MONOTONIC, &now)) return -1;
        if (now.tv_sec > deadline.tv_sec ||
            (now.tv_sec == deadline.tv_sec && now.tv_nsec >= deadline.tv_nsec)) {
            errno = ETIMEDOUT;
            return -1;
        }
        if (nanosleep(&pause, NULL) && errno != EINTR) return -1;
    }
}

static int probe_extension(const char *name, int akv, size_t count) {
    int pipefd[2];
    if (pipe(pipefd)) {
        printf("[LINUX_CUSTOM_CAPS] %s ERROR pipe errno=%d\n", name, errno);
        return 1;
    }
    pid_t child = fork();
    if (child < 0) {
        int error = errno;
        close(pipefd[0]);
        close(pipefd[1]);
        printf("[LINUX_CUSTOM_CAPS] %s ERROR fork errno=%d\n", name, error);
        return 1;
    }
    if (child == 0) {
        close(pipefd[0]);
        probe_child(pipefd[1], akv, count);
        _exit(1);
    }
    close(pipefd[1]);

    /* At most 32 bytes fit atomically in an empty pipe; reap before reading. */
    int status;
    if (wait_bounded(child, &status)) {
        int error = errno;
        kill(child, SIGKILL);
        while (waitpid(child, &status, 0) < 0 && errno == EINTR) {}
        close(pipefd[0]);
        printf("[LINUX_CUSTOM_CAPS] %s ERROR %s errno=%d\n", name,
               error == ETIMEDOUT ? "timeout" : "wait", error);
        return 1;
    }
    if (WIFSIGNALED(status)) {
        int sig = WTERMSIG(status);
        close(pipefd[0]);
        if (sig == SIGILL) {
            printf("[LINUX_CUSTOM_CAPS] %s UNAVAILABLE signal=SIGILL\n", name);
            return 0;
        }
        printf("[LINUX_CUSTOM_CAPS] %s ERROR %s signal=%d\n", name,
               sig == SIGALRM ? "timeout" : "child", sig);
        return 1;
    }
    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        close(pipefd[0]);
        printf("[LINUX_CUSTOM_CAPS] %s ERROR child_status=0x%x\n", name, status);
        return 1;
    }

    unsigned char payload[4 * sizeof(uint64_t) + 1];
    const size_t expected = count * sizeof(uint64_t);
    size_t received = 0;
    int error = 0;
    while (received < expected + 1) {
        ssize_t n = read(pipefd[0], payload + received, expected + 1 - received);
        if (n < 0) {
            if (errno == EINTR) continue;
            error = errno;
            break;
        }
        if (n == 0) break;
        received += (size_t)n;
    }
    close(pipefd[0]);
    if (error || received != expected) {
        printf("[LINUX_CUSTOM_CAPS] %s ERROR payload_bytes=%zu expected=%zu "
               "errno=%d\n", name, received, expected, error);
        return 1;
    }
    for (size_t i = 0; i < count; ++i) {
        uint64_t word;
        memcpy(&word, payload + i * sizeof(word), sizeof(word));
        printf("[LINUX_CUSTOM_CAPS] %s RAW index=%zu word=0x%016" PRIx64 "\n",
               name, i, word);
    }
    return 0;
}

int custom_caps_probe(void) {
    int failed = probe_extension("QBS", 0, 3);
    failed |= probe_extension("AKV", 1, 4);
    puts("CUSTOM_COMPUTE=NOT_VALIDATED");
    return failed ? 1 : 0;
}
