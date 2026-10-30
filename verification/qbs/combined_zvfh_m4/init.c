#include <stdio.h>
#include <stdlib.h>
#include <sys/reboot.h>
#include <sys/wait.h>
#include <unistd.h>

int main(void) {
    setvbuf(stdout, NULL, _IONBF, 0);
    int result = 0;
    for (unsigned mode = 0; mode < 2 && !result; ++mode) {
        printf("Q8K_COMBINED_MODE_BEGIN mode=%u\n", mode);
        pid_t child = fork();
        if (!child) {
            if (setenv("GGML_RISCV_QBS_M4_PREPARE", mode ? "1" : "0", 1) ||
                setenv("GGML_RISCV_QBS_TRACE_M4_PREPARE", "1", 1)) _exit(126);
            execl("/native", "/native", "/captures.txt", NULL);
            _exit(127);
        }
        int status = 0;
        if (child < 0 || waitpid(child, &status, 0) != child) result = 127;
        else result = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
        printf("Q8K_COMBINED_MODE_END mode=%u exit=%d\n", mode, result);
    }
    printf("Q8K_COMBINED_GUEST_EXIT=%d\n", result);
    fflush(NULL);
    sync();
    reboot(RB_POWER_OFF);
    for (;;) pause();
}
