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

static int run(unsigned automatic) {
    const pid_t child = fork();
    if (!child) {
        if (clearenv() || setenv("PATH", "/bin:/usr/bin", 1) ||
            setenv("LC_ALL", "C", 1) || setenv("GGML_RISCV_QBS_TRACE", "1", 1) ||
            setenv("GGML_RISCV_AKV_TRACE", "1", 1) ||
            setenv("LLAMA_SIMPLE_LOGITS_FILE", automatic ? "/tmp/auto.bin" : "/tmp/manual.bin", 1))
            _exit(126);
        if (!automatic) {
            const char * const enabled[] = {
                "GGML_RISCV_QBS", "GGML_RISCV_AKV",
                "GGML_RISCV_QBS_ACTIVATION_CONTEXT", "GGML_RISCV_QBS_CROSS_OP_CONTEXT",
                "GGML_RISCV_QBS_M4_PREPARE", "GGML_RISCV_QBS_M4_PACKED",
                "GGML_RISCV_QBS_M4_PARALLEL_SUMS", "GGML_RISCV_QBS_M4_CACHE",
                "GGML_RISCV_AKV_QUANT_KV", "GGML_RISCV_AKV_QUANT_PREFILL",
                "GGML_RISCV_AKV_REGISTER_PV", NULL,
            };
            for (unsigned i = 0; enabled[i]; ++i)
                if (setenv(enabled[i], "1", 1)) _exit(126);
            if (setenv("GGML_RISCV_ACCEL_AUTO", "0", 1) ||
                setenv("GGML_RISCV_AKV_KERNEL", "auto", 1)) _exit(126);
        }
        char * const argv[] = {"/test", "-m",
            "/model/models/SmolLM2-135M-Instruct-Q4_K_M.gguf",
            "-n", "2", "-ngl", "0", "The capital of France is", NULL};
        execv(argv[0], argv);
        _exit(127);
    }
    if (child < 0) return 125;
    int status;
    pid_t waited;
    do { waited = waitpid(child, &status, 0); } while (waited < 0 && errno == EINTR);
    return waited == child && WIFEXITED(status) ? WEXITSTATUS(status) : 124;
}

static int compare(void) {
    FILE * a = fopen("/tmp/manual.bin", "rb"), * b = fopen("/tmp/auto.bin", "rb");
    if (!a || !b) return 1;
    unsigned records = 0, values = 0;
    for (;;) {
        uint32_t ha[6], hb[6];
        const size_t na = fread(ha, 1, sizeof(ha), a), nb = fread(hb, 1, sizeof(hb), b);
        if (!na && !nb) break;
        if (na != sizeof(ha) || nb != sizeof(hb) || memcmp(ha, hb, sizeof(ha)) ||
            ha[0] != 0x5142534c || ha[1] != 2 || ha[2] != records ||
            ha[3] != 49152 || ha[5]) return 2;
        uint32_t remaining = ha[3];
        while (remaining) {
            uint32_t va[1024], vb[1024];
            const size_t n = remaining < 1024 ? remaining : 1024;
            if (fread(va, sizeof(*va), n, a) != n || fread(vb, sizeof(*vb), n, b) != n ||
                memcmp(va, vb, n * sizeof(*va))) return 3;
            for (size_t i = 0; i < n; ++i)
                if ((va[i] & 0x7f800000u) == 0x7f800000u) return 4;
            remaining -= n;
            values += n;
        }
        ++records;
    }
    if (ferror(a) || ferror(b) || records != 2) return 5;
    fclose(a); fclose(b);
    printf("AUTO_MODEL_LOGITS_PASS records=%u values=%u bitwise=1\n", records, values);
    return 0;
}

int main(void) {
    int result = 127;
    setvbuf(stdout, NULL, _IONBF, 0); setvbuf(stderr, NULL, _IONBF, 0);
    if (getpid() == 1 &&
        !mount("devtmpfs", "/dev", "devtmpfs", MS_NOSUID, NULL) &&
        !mount("proc", "/proc", "proc", MS_NOSUID | MS_NOEXEC | MS_NODEV, NULL)) {
        for (unsigned i = 0; i < 100 && access("/dev/vda", F_OK); ++i) usleep(100000);
        if (!mount("/dev/vda", "/model", "ext4", MS_RDONLY | MS_NODEV | MS_NOSUID | MS_NOEXEC, NULL)) {
            result = 0;
            for (unsigned mode = 0; mode < 2 && !result; ++mode) {
                printf("AUTO_MODEL_BEGIN automatic=%u\n", mode);
                result = run(mode);
                printf("AUTO_MODEL_END automatic=%u status=%d\n", mode, result);
            }
            if (!result) result = compare();
        }
    }
    printf("GUEST_TEST_EXIT=%d\n", result);
    fflush(NULL); sync(); reboot(RB_POWER_OFF);
    for (;;) pause();
}
