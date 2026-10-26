#include <stdio.h>
#include <sys/reboot.h>
#include <sys/wait.h>
#include <unistd.h>

int main(void) {
    setvbuf(stdout, NULL, _IONBF, 0);
    pid_t child = fork();
    if (!child) {
        execl("/native", "/native", NULL);
        _exit(127);
    }
    int status = 0;
    int result = 127;
    if (child > 0 && waitpid(child, &status, 0) == child)
        result = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
    printf("VCSR_DIAG_GUEST_EXIT=%d\n", result);
    fflush(NULL);
    sync();
    reboot(RB_POWER_OFF);
    for (;;) pause();
}
