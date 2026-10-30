#include <stdio.h>
#include <stdlib.h>
#include <sys/reboot.h>
#include <sys/wait.h>
#include <unistd.h>

static void env(const char *name, const char *value) {
  if (setenv(name, value, 1)) _exit(126);
}

int main(void) {
  setvbuf(stdout, NULL, _IONBF, 0);
  const char *contexts[] = {"0", "1", "0", "1", "0", "1"};
  const char *wide[] = {"0", "0", "1", "1", "1", "1"};
  const char *threads[] = {"1", "1", "1", "1", "3", "3"};
  int result = 0;
  for (unsigned prepare = 0; !result && prepare < 2; ++prepare) {
    printf("Q8K_GRAPH_GROUP_BEGIN prepare=%u\n", prepare);
    for (unsigned run = 0; !result && run < 6; ++run) {
      printf("QBS_TILE_RUN_BEGIN run=%u context=%s wide=%s threads=%s\n",
             run, contexts[run], wide[run], threads[run]);
      pid_t child = fork();
      if (!child) {
        env("GGML_RISCV_QBS", "1");
        env("GGML_RISCV_QBS_EMULATE", "0");
        env("GGML_RISCV_QBS_M4_PREPARE", prepare ? "1" : "0");
        env("GGML_RISCV_QBS_TRACE_M4_PREPARE", "1");
        env("GGML_RISCV_QBS_ACTIVATION_CONTEXT", contexts[run]);
        env("GGML_RISCV_QBS_CROSS_OP_CONTEXT", "0");
        env("GGML_RISCV_QBS_WIDE_M", wide[run]);
        env("GGML_RISCV_QBS_SEGMENT_K_BLOCKS", "256");
        env("GGML_RISCV_QBS_TRACE", "1");
        env("GGML_RISCV_QBS_TRACE_CALLS", "1");
        env("GGML_RISCV_QBS_TRACE_LIFETIME", "1");
        env("GGML_QBS_TILE_THREADS", threads[run]);
        execl("/graph", "/graph", NULL);
        _exit(127);
      }
      int status = 0;
      if (child < 0 || waitpid(child, &status, 0) != child) result = 127;
      else result = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
      printf("QBS_TILE_RUN_END run=%u exit=%d\n", run, result);
    }
    printf("GUEST_TEST_EXIT=%d\n", result);
    printf("Q8K_GRAPH_GROUP_END prepare=%u exit=%d\n", prepare, result);
  }
  printf("Q8K_GRAPH_GUEST_EXIT=%d\n", result);
  fflush(NULL);
  sync();
  reboot(RB_POWER_OFF);
  for (;;) pause();
}
