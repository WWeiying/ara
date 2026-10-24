#include <stdio.h>
#include <sys/reboot.h>
#include <sys/wait.h>
#include <unistd.h>

int main(void) {
    pid_t child = fork();
    if (child == 0) {
        execl("/test", "/test", NULL);
        perror("exec /test");
        _exit(127);
    }
    int status;
    int result = child < 0 || waitpid(child, &status, 0) != child ? 127 :
        WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
    printf("GUEST_TEST_EXIT=%d\n", result);
    fflush(NULL);
    sync();
    reboot(RB_POWER_OFF);
    for (;;) pause();
}
