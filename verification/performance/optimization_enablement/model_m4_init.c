#define _GNU_SOURCE
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/wait.h>
#include <unistd.h>

static const char prompt[] = "Explain how a vector processor uses parallel arithmetic and memory bandwidth to perform quantized matrix multiplication when generating text with a language model.";

static int run(unsigned mode) {
    const pid_t child = fork();
    if (!child) {
        if (clearenv() || setenv("PATH", "/bin:/usr/bin", 1) || setenv("LC_ALL", "C", 1)) _exit(126);
        const char *const keys[] = {"GGML_RISCV_ACCEL_AUTO", "GGML_RISCV_QBS_TRACE",
            "GGML_RISCV_AKV_TRACE", "GGML_RISCV_QBS_TRACE_M4_PREPARE", NULL};
        for (unsigned i = 0; keys[i]; ++i) if (setenv(keys[i], "1", 1)) _exit(126);
        if (setenv("GGML_RISCV_QBS_M4_PREFLIGHT", mode ? "1" : "0", 1) ||
            setenv("LLAMA_SIMPLE_LOGITS_FILE", "/tmp/logits.bin", 1)) _exit(126);
        char *const argv[] = {"/test", "-m", "/model/models/qwen2.5-1.5b-instruct-q4_k_m.gguf",
            "-n", "2", "-t", "1", "-ngl", "0", (char *)prompt, NULL};
        execv(argv[0], argv); _exit(127);
    }
    if (child < 0) return 125;
    int status; pid_t waited;
    do { waited = waitpid(child, &status, 0); } while (waited < 0 && errno == EINTR);
    return waited == child && WIFEXITED(status) ? WEXITSTATUS(status) : 124;
}

static int capture(unsigned mode) {
    FILE *f = fopen("/tmp/logits.bin", "rb");
    if (!f) return 1;
    for (unsigned step = 0; step < 2; ++step) {
        uint32_t h[6];
        if (fread(h, sizeof(*h), 6, f) != 6 || h[0] != 0x5142534c || h[1] != 2 ||
            h[2] != step || h[3] != 151936 || h[4] != UINT32_MAX || h[5]) return 2;
        printf("M4_LOGITS_BEGIN mode=%u step=%u values=%u\n", mode, step, h[3]);
        for (unsigned at = 0; at < h[3]; at += 32) {
            uint32_t values[32]; const unsigned count = h[3] - at < 32 ? h[3] - at : 32;
            if (fread(values, sizeof(*values), count, f) != count) return 3;
            printf("M4_BITS index=%u", at);
            for (unsigned i = 0; i < count; ++i) {
                if ((values[i] & 0x7f800000u) == 0x7f800000u) return 4;
                printf(" %08x", values[i]);
            }
            putchar('\n');
        }
        printf("M4_LOGITS_END mode=%u step=%u\n", mode, step);
    }
    int rc = fgetc(f) != EOF || ferror(f); fclose(f);
    if (unlink("/tmp/logits.bin")) return 5;
    return rc;
}

int main(void) {
    int result = 127;
    setvbuf(stdout, NULL, _IONBF, 0); setvbuf(stderr, NULL, _IONBF, 0);
    if (getpid() == 1 && !mount("devtmpfs", "/dev", "devtmpfs", MS_NOSUID, NULL) &&
        !mount("proc", "/proc", "proc", MS_NOSUID | MS_NOEXEC | MS_NODEV, NULL)) {
        for (unsigned i = 0; i < 100 && access("/dev/vda", F_OK); ++i) usleep(100000);
        if (!mount("/dev/vda", "/model", "ext4", MS_RDONLY | MS_NODEV | MS_NOSUID | MS_NOEXEC, NULL)) {
            result = 0;
            for (unsigned mode = 0; mode < 2 && !result; ++mode) {
                printf("M4_ARM_BEGIN mode=%u\n", mode);
                result = run(mode);
                if (!result) result = capture(mode);
                printf("M4_ARM_END mode=%u status=%d\n", mode, result);
            }
        }
    }
    printf("GUEST_TEST_EXIT=%d\n", result);
    fflush(NULL); sync(); reboot(RB_POWER_OFF); for (;;) pause();
}
