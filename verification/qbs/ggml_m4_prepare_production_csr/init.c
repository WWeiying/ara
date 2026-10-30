#include <stdio.h>
#include <stdlib.h>
#include <sys/reboot.h>
#include <sys/wait.h>
#include <unistd.h>

int main(void) {
    setvbuf(stdout, NULL, _IONBF, 0);
    int result = 0;
    for (unsigned run = 0; run < 4 && !result; ++run) {
        const unsigned mode = run / 2, trace = run % 2;
        printf("M4_TU_RUN_BEGIN run=%u mode=%u trace=%u\n", run, mode, trace);
        pid_t child = fork();
        if (child == 0) {
            if (setenv("GGML_RISCV_QBS_M4_PREPARE", mode ? "1" : "0", 1) ||
                setenv("GGML_RISCV_QBS_TRACE_M4_PREPARE", trace ? "1" : "0", 1))
                _exit(126);
            execl("/test", "/test", "/capture.bin", NULL);
            _exit(127);
        }
        int status;
        if (child < 0 || waitpid(child, &status, 0) != child) result = 127;
        else result = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
        printf("M4_TU_RUN_END run=%u exit=%d\n", run, result);
    }
    printf("M4_TU_GUEST_EXIT=%d\n", result);
    fflush(NULL);
    sync();
    reboot(RB_POWER_OFF);
    for (;;) pause();
}
