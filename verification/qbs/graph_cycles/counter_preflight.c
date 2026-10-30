#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>
#include "linux_counter.h"

/* Minimal guest init: test user access without loading a model. */
int main(void) {
    int status = 0, access_mode = -1;
    const struct rlimit no_core = {0, 0};
    setrlimit(RLIMIT_CORE, &no_core);
    if (mount("proc", "/proc", "proc", 0, NULL) != 0) {
        perror("proc mount");
    } else {
        FILE *f = fopen("/proc/sys/kernel/perf_user_access", "r");
        if (f) {
            if (fscanf(f, "%d", &access_mode) != 1) access_mode = -1;
            fclose(f);
        }
    }
    printf("COUNTER_ACCESS mode=%d\n", access_mode);
    int counter_fd = -1;
    if (access_mode == 2) {
        counter_fd = graph_cycles_linux_counter_start();
        if (counter_fd < 0) perror("perf_event_open");
        printf("COUNTER_EVENT active=%d\n", counter_fd >= 0);
    }
    fflush(NULL);
    pid_t child = fork();
    if (child == 0) {
        uint64_t begin, end;
        __asm__ volatile("rdcycle %0" : "=r"(begin) :: "memory");
        for (volatile unsigned i = 0; i < 10000; ++i) {}
        __asm__ volatile("rdcycle %0" : "=r"(end) :: "memory");
        printf("COUNTER_READ begin=%" PRIu64 " end=%" PRIu64 "\n", begin, end);
        fflush(NULL);
        _exit(end > begin ? 0 : 2);
    }
    if (child > 0 && waitpid(child, &status, 0) == child) {
        printf("COUNTER_CHILD exit=%d signal=%d\n",
               WIFEXITED(status) ? WEXITSTATUS(status) : -1,
               WIFSIGNALED(status) ? WTERMSIG(status) : 0);
    } else {
        puts("COUNTER_CHILD_ERROR");
    }
    fflush(NULL);
    if (counter_fd >= 0) close(counter_fd);
    reboot(RB_POWER_OFF);
    for (;;) pause();
}
