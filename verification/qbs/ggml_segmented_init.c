#include <stdio.h>
#include <stdlib.h>
#include <sys/reboot.h>
#include <sys/wait.h>
#include <unistd.h>

int main(void) {
    const char * segments[] = {"0", "3", "256", "3"};
    const char * wide[] = {"0", "0", "1", "1"};
    int result = 0;
    for (unsigned run = 0; run < 4; ++run) {
        printf("QBS_GRAPH_RUN_BEGIN segment=%s wide=%s\n", segments[run], wide[run]);
        fflush(NULL);
        const pid_t child = fork();
        if (child == 0) {
            setenv("GGML_RISCV_QBS_EMULATE", "1", 1);
            setenv("GGML_RISCV_QBS_TRACE", "1", 1);
            setenv("GGML_RISCV_QBS_TRACE_CALLS", "1", 1);
            setenv("GGML_RISCV_QBS_TRACE_LIFETIME", "1", 1);
            setenv("GGML_RISCV_QBS_SEGMENT_K_BLOCKS", segments[run], 1);
            setenv("GGML_RISCV_QBS_WIDE_M", wide[run], 1);
            execl("/test", "/test", NULL);
            perror("exec /test");
            _exit(127);
        }
        int status = 0;
        if (child < 0 || waitpid(child, &status, 0) != child) {
            perror("fork/waitpid");
            result = 127;
        } else {
            result = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
        }
        printf("QBS_GRAPH_RUN_END segment=%s wide=%s exit=%d\n", segments[run], wide[run], result);
        fflush(NULL);
        if (result) {
            break;
        }
    }
    printf("GUEST_TEST_EXIT=%d\n", result);
    fflush(NULL);
    sync();
    reboot(RB_POWER_OFF);
    for (;;) {
        pause();
    }
}
