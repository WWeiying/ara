#include <stdio.h>
#include <stdlib.h>
#include <sys/reboot.h>
#include <sys/wait.h>
#include <unistd.h>

int main(void) {
    const char *contexts[] = {"0", "1", "0", "1", "0", "1"};
    const char *wide[] = {"0", "0", "1", "1", "1", "1"};
    const char *threads[] = {"1", "1", "1", "1", "3", "3"};
    int result = 0;
    for (unsigned run = 0; run < sizeof(contexts) / sizeof(contexts[0]); ++run) {
        printf("QBS_TILE_RUN_BEGIN run=%u context=%s wide=%s threads=%s\n",
               run, contexts[run], wide[run], threads[run]);
        fflush(NULL);
        pid_t child = fork();
        if (child == 0) {
            setenv("GGML_RISCV_QBS", "1", 1);
            setenv("GGML_RISCV_QBS_EMULATE", "0", 1);
            setenv("GGML_RISCV_QBS_ACTIVATION_CONTEXT", contexts[run], 1);
            setenv("GGML_RISCV_QBS_CROSS_OP_CONTEXT", "0", 1);
            setenv("GGML_RISCV_QBS_WIDE_M", wide[run], 1);
            setenv("GGML_RISCV_QBS_SEGMENT_K_BLOCKS", "256", 1);
            setenv("GGML_RISCV_QBS_TRACE", "1", 1);
            setenv("GGML_RISCV_QBS_TRACE_CALLS", "1", 1);
            setenv("GGML_RISCV_QBS_TRACE_LIFETIME", "1", 1);
            setenv("GGML_QBS_TILE_THREADS", threads[run], 1);
            execl("/test", "/test", NULL);
            perror("exec /test");
            _exit(127);
        }
        int status;
        if (child < 0 || waitpid(child, &status, 0) != child) {
            perror("fork/waitpid");
            result = 127;
        } else {
            result = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
        }
        printf("QBS_TILE_RUN_END run=%u exit=%d\n", run, result);
        fflush(NULL);
        if (result) break;
    }
    printf("GUEST_TEST_EXIT=%d\n", result);
    fflush(NULL);
    sync();
    reboot(RB_POWER_OFF);
    for (;;) pause();
}
