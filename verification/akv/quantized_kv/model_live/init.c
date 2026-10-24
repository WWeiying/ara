#include <stdio.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/wait.h>
#include <unistd.h>

int main(void) {
    int result = 127;
    if (mount("devtmpfs", "/dev", "devtmpfs", 0, NULL) != 0) {
        perror("devtmpfs");
    } else {
        for (unsigned retry = 0; retry < 100 && access("/dev/vda", F_OK) != 0; ++retry) usleep(100000);
        if (mount("/dev/vda", "/model", "ext4", MS_RDONLY, NULL) != 0) {
            perror("model mount");
        } else {
            pid_t child = fork();
            if (child == 0) {
                execl("/test", "/test", NULL);
                perror("exec test");
                _exit(127);
            }
            int status;
            if (child > 0 && waitpid(child, &status, 0) == child) {
                result = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
            }
        }
    }
    printf("GUEST_TEST_EXIT=%d\n", result);
    fflush(NULL);
    sync();
    reboot(RB_POWER_OFF);
    for (;;) pause();
}
