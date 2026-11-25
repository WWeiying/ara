#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/wait.h>
#include <unistd.h>

static int run(const char *name, const char *enabled, const char *logits) {
    fflush(NULL);
    const pid_t child = fork();
    if (child < 0) return 127;
    if (!child) {
        setenv("GGML_RISCV_ACCEL_AUTO", "0", 1);
        setenv("GGML_RISCV_QBS", "0", 1);
        setenv("GGML_RISCV_QBS_EMULATE", "0", 1);
        setenv("GGML_RISCV_AKV", enabled, 1);
        setenv("GGML_RISCV_AKV_EMULATE", "0", 1);
        setenv("GGML_RISCV_AKV_RESIDENT", "1", 1);
        setenv("GGML_RISCV_AKV_TRACE", "1", 1);
        setenv("LLAMA_SIMPLE_LOGITS_FILE", logits, 1);
        execl("/llama-simple", "/llama-simple", "-m", "/model.gguf", "-n", "4",
              "-ngl", "0", "-t", "1", "-fa", "on", "--kv-type", "f16",
              "The capital of France is", (char *)NULL);
        _exit(127);
    }
    int status = 0;
    while (waitpid(child, &status, 0) < 0) if (errno != EINTR) return 127;
    const int rc = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
    printf("DIRECT_MODEL_FALLBACK_CASE name=%s exit=%d\n", name, rc);
    return rc;
}

int main(void) {
    int failed = mount("devtmpfs", "/dev", "devtmpfs", 0, NULL) != 0;
    failed |= mount("proc", "/proc", "proc", 0, NULL) != 0;
    failed |= mount("sysfs", "/sys", "sysfs", 0, NULL) != 0;
    if (!failed) {
        failed |= run("rvv", "0", "/rvv.logits");
        failed |= run("direct-unavailable", "1", "/direct.logits");
    }
    FILE *a = fopen("/rvv.logits", "rb"), *b = fopen("/direct.logits", "rb");
    size_t bytes = 0;
    if (!a || !b) failed = 1;
    else {
        for (;;) {
            const int x = fgetc(a), y = fgetc(b);
            if (x != y) { failed = 1; break; }
            if (x == EOF) break;
            ++bytes;
        }
        failed |= ferror(a) || ferror(b) || bytes == 0;
    }
    if (a) fclose(a);
    if (b) fclose(b);
    printf("DIRECT_MODEL_FALLBACK_RESULT exit=%d identical_logit_bytes=%zu\n", !!failed, bytes);
    fflush(NULL);
    sync();
    reboot(RB_POWER_OFF);
    for (;;) pause();
}
