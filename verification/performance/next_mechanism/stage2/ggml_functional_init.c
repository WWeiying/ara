#include <stdio.h>
#include <sys/reboot.h>
#include <sys/wait.h>
#include <unistd.h>
#ifndef ARM_NAME
#error ARM_NAME_required
#endif
int main(void) {
  setvbuf(stdout, NULL, _IONBF, 0);
  pid_t child = fork();
  if (child == 0) {
    execl("/test", "/test", ARM_NAME, (char *)0);
    _exit(127);
  }
  int status = 0, code = 127;
  if (child > 0 && waitpid(child, &status, 0) == child)
    code = WIFEXITED(status) ? WEXITSTATUS(status) : 128+WTERMSIG(status);
  printf("G4_EXIT arm=%s code=%d\n", ARM_NAME, code);
  sync(); reboot(RB_POWER_OFF);
  for (;;) pause();
}
