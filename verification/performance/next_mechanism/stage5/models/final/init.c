#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/wait.h>
#include <unistd.h>

/* Same read-only model-disk / static-initramfs flow as model_live/init.c. */
int main(void) {
    int result = 127;
    setvbuf(stdout, NULL, _IONBF, 0); setvbuf(stderr, NULL, _IONBF, 0);
    if (getpid() != 1 || mount("devtmpfs", "/dev", "devtmpfs", MS_NOSUID, NULL) ||
        mount("proc", "/proc", "proc", MS_NOSUID|MS_NOEXEC|MS_NODEV, NULL)) {
        perror("execution init mounts");
    } else {
        for (unsigned retry = 0; retry < 100 && access("/dev/vda", F_OK); ++retry) usleep(100000);
        if (mount("/dev/vda", "/model", "ext4", MS_RDONLY|MS_NODEV|MS_NOSUID|MS_NOEXEC, NULL)) {
            perror("read-only model mount");
        } else {
            pid_t child = fork();
            if (!child) {
                char *const argv[] = {"/test", NULL}, *const env[] = {"PATH=/bin:/usr/bin", "LC_ALL=C", NULL};
                execve("/test", argv, env); perror("exec /test"); _exit(127);
            }
            int status; pid_t waited;
            do { waited = waitpid(child, &status, 0); } while (waited < 0 && errno == EINTR);
            if (child > 0 && waited == child)
                result = WIFEXITED(status) ? WEXITSTATUS(status) : WIFSIGNALED(status) ? 128+WTERMSIG(status) : 126;
        }
    }
    printf("GUEST_TEST_EXIT=%d\n", result);
    fflush(NULL); sync(); reboot(RB_POWER_OFF);
    for (;;) pause();
}
