#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/wait.h>
#include <unistd.h>

#define LOGITS_DUMP_MAGIC 0x5142534cU

#ifndef AKV_LOGITS_MAX_ABS_TOLERANCE
#define AKV_LOGITS_MAX_ABS_TOLERANCE 0.001
#endif

struct logits_dump_record {
    uint32_t magic;
    uint32_t version;
    uint32_t step;
    uint32_t n_vocab;
    int32_t target_token;
    uint32_t reserved;
};

struct logits_comparison {
    int valid;
    int top1_equal;
    uint32_t records;
    float max_abs;
    float max_rel;
};

struct run_result {
    int exit_code;
    size_t output_size;
    size_t output_capacity;
    char * output;
    int capture_failed;
};

static float absf(float value) {
    return value < 0.0f ? -value : value;
}

static int finite_f32(float value) {
    uint32_t bits;
    memcpy(&bits, &value, sizeof(bits));
    return (bits & UINT32_C(0x7f800000)) != UINT32_C(0x7f800000);
}

static int same_record(const struct logits_dump_record * lhs,
                       const struct logits_dump_record * rhs) {
    return lhs->magic == LOGITS_DUMP_MAGIC && rhs->magic == LOGITS_DUMP_MAGIC &&
           lhs->version == 2 && rhs->version == 2 &&
           lhs->step == rhs->step && lhs->n_vocab == rhs->n_vocab &&
           lhs->target_token == rhs->target_token &&
           lhs->reserved == 0 && rhs->reserved == 0 && lhs->n_vocab > 0;
}

static struct logits_comparison compare_logits(const char * rvv_path,
                                                const char * akv_path) {
    struct logits_comparison result = {
        .valid = 0,
        .top1_equal = 1,
        .records = 0,
        .max_abs = 0.0f,
        .max_rel = 0.0f,
    };
    FILE * rvv_file = fopen(rvv_path, "rb");
    FILE * akv_file = fopen(akv_path, "rb");
    float * rvv_logits = NULL;
    float * akv_logits = NULL;

    if (rvv_file == NULL || akv_file == NULL) {
        perror("open logits");
        goto cleanup;
    }

    for (;;) {
        struct logits_dump_record rvv_record;
        struct logits_dump_record akv_record;
        const size_t rvv_bytes = fread(&rvv_record, 1, sizeof(rvv_record), rvv_file);
        const size_t akv_bytes = fread(&akv_record, 1, sizeof(akv_record), akv_file);
        if (rvv_bytes == 0 || akv_bytes == 0) {
            if (rvv_bytes == 0 && akv_bytes == 0 && feof(rvv_file) && feof(akv_file)) {
                result.valid = result.records > 0;
            }
            break;
        }
        if (rvv_bytes != sizeof(rvv_record) || akv_bytes != sizeof(akv_record) ||
            !same_record(&rvv_record, &akv_record) ||
            rvv_record.n_vocab > UINT32_C(16777216)) {
            break;
        }

        const size_t bytes = (size_t) rvv_record.n_vocab * sizeof(float);
        rvv_logits = malloc(bytes);
        akv_logits = malloc(bytes);
        if (rvv_logits == NULL || akv_logits == NULL ||
            fread(rvv_logits, sizeof(float), rvv_record.n_vocab, rvv_file) != rvv_record.n_vocab ||
            fread(akv_logits, sizeof(float), akv_record.n_vocab, akv_file) != akv_record.n_vocab) {
            break;
        }

        uint32_t rvv_top = 0;
        uint32_t akv_top = 0;
        for (uint32_t index = 0; index < rvv_record.n_vocab; ++index) {
            if (!finite_f32(rvv_logits[index]) || !finite_f32(akv_logits[index])) {
                goto cleanup;
            }
            if (rvv_logits[index] > rvv_logits[rvv_top]) {
                rvv_top = index;
            }
            if (akv_logits[index] > akv_logits[akv_top]) {
                akv_top = index;
            }
            const float absolute = absf(akv_logits[index] - rvv_logits[index]);
            const float scale = absf(rvv_logits[index]) > 1.0e-6f ? absf(rvv_logits[index]) : 1.0e-6f;
            const float relative = absolute / scale;
            if (absolute > result.max_abs) {
                result.max_abs = absolute;
            }
            if (relative > result.max_rel) {
                result.max_rel = relative;
            }
        }
        result.top1_equal &= rvv_top == akv_top;
        ++result.records;
        free(rvv_logits);
        free(akv_logits);
        rvv_logits = NULL;
        akv_logits = NULL;
    }

cleanup:
    free(rvv_logits);
    free(akv_logits);
    if (rvv_file != NULL) {
        fclose(rvv_file);
    }
    if (akv_file != NULL) {
        fclose(akv_file);
    }
    return result;
}

static int wait_for_device(const char * path) {
    for (int retry = 0; retry < 100; ++retry) {
        if (access(path, F_OK) == 0) {
            return 0;
        }
        usleep(100000);
    }
    fprintf(stderr, "device timeout: %s\n", path);
    return -1;
}

static void append_output(struct run_result * result, const char * data,
                          size_t data_size) {
    if (result->capture_failed || data_size == 0) {
        return;
    }
    if (data_size > SIZE_MAX - result->output_size) {
        result->capture_failed = 1;
        return;
    }

    const size_t required = result->output_size + data_size;
    if (required > result->output_capacity) {
        size_t capacity = result->output_capacity == 0 ? 4096 : result->output_capacity;
        while (capacity < required) {
            if (capacity > SIZE_MAX / 2) {
                capacity = required;
                break;
            }
            capacity *= 2;
        }
        char * output = realloc(result->output, capacity);
        if (output == NULL) {
            result->capture_failed = 1;
            return;
        }
        result->output = output;
        result->output_capacity = capacity;
    }

    memcpy(result->output + result->output_size, data, data_size);
    result->output_size = required;
}

static struct run_result run_variant(const char * label, int emulate) {
    struct run_result result = { .exit_code = 127 };
    int output_pipe[2];
    if (pipe(output_pipe) != 0) {
        perror("pipe");
        return result;
    }

    printf("AKV_TOKEN_RUN_BEGIN=%s\n", label);
    fflush(stdout);

    const pid_t child = fork();
    if (child == 0) {
        close(output_pipe[0]);
        if (dup2(output_pipe[1], STDOUT_FILENO) < 0) {
            perror("dup2");
            _exit(126);
        }
        close(output_pipe[1]);

        unsetenv("GGML_RISCV_QBS");
        unsetenv("GGML_RISCV_QBS_EMULATE");
        unsetenv("GGML_RISCV_QBS_TRACE");
        unsetenv("GGML_RISCV_AKV");
        unsetenv("GGML_RISCV_AKV_EMULATE");
        setenv("GGML_RISCV_AKV_TRACE", "1", 1);
        if (emulate) {
            setenv("GGML_RISCV_AKV_EMULATE", "1", 1);
        }
        setenv("LLAMA_SIMPLE_LOGITS_FILE",
               emulate ? "/akv-emulate.logits" : "/rvv.logits", 1);

        execl("/run/llama-simple", "/run/llama-simple",
              "-m", "/model/models/qwen2.5-1.5b-instruct-q4_k_m.gguf",
              "-n", "2", "-ngl", "0",
              "The quick brown fox jumps over the lazy dog.", NULL);
        perror("exec llama-simple");
        _exit(127);
    }

    close(output_pipe[1]);
    if (child < 0) {
        perror("fork");
        close(output_pipe[0]);
        return result;
    }

    for (;;) {
        char chunk[4096];
        const ssize_t count = read(output_pipe[0], chunk, sizeof(chunk));
        if (count > 0) {
            append_output(&result, chunk, (size_t) count);
        } else if (count == 0) {
            break;
        } else if (errno != EINTR) {
            perror("read child output");
            result.capture_failed = 1;
            break;
        }
    }
    close(output_pipe[0]);

    int status = 0;
    if (waitpid(child, &status, 0) < 0) {
        perror("waitpid");
    } else if (WIFEXITED(status)) {
        result.exit_code = WEXITSTATUS(status);
    } else if (WIFSIGNALED(status)) {
        result.exit_code = 128 + WTERMSIG(status);
    }

    printf("AKV_TOKEN_RUN_EXIT=%s:%d\n", label, result.exit_code);
    printf("AKV_TOKEN_OUTPUT_BEGIN=%s\n", label);
    if (result.output_size != 0) {
        fwrite(result.output, 1, result.output_size, stdout);
    }
    if (result.output_size == 0 || result.output[result.output_size - 1] != '\n') {
        putchar('\n');
    }
    printf("AKV_TOKEN_OUTPUT_END=%s\n", label);
    fflush(stdout);
    return result;
}

int main(void) {
    if (mount("devtmpfs", "/dev", "devtmpfs", 0, NULL) != 0) {
        perror("mount devtmpfs");
        return 1;
    }
    if (wait_for_device("/dev/vda") != 0 || wait_for_device("/dev/vdb") != 0) {
        return 1;
    }
    if (mount("/dev/vda", "/run", "ext4", MS_RDONLY, NULL) != 0) {
        perror("mount binary disk");
        return 1;
    }
    if (mount("/dev/vdb", "/model", "ext4", MS_RDONLY, NULL) != 0) {
        perror("mount model disk");
        return 1;
    }

    unlink("/rvv.logits");
    unlink("/akv-emulate.logits");
    const struct run_result rvv = run_variant("RVV", 0);
    const struct run_result akv = run_variant("AKV_EMULATE", 1);
    const struct logits_comparison logits =
        compare_logits("/rvv.logits", "/akv-emulate.logits");
    const int text_equal = !rvv.capture_failed && !akv.capture_failed &&
                           rvv.exit_code == 0 && akv.exit_code == 0 &&
                           rvv.output_size == akv.output_size &&
                           (rvv.output_size == 0 ||
                            memcmp(rvv.output, akv.output, rvv.output_size) == 0);
    const int passed = text_equal && logits.valid && logits.top1_equal &&
                       logits.max_abs <= AKV_LOGITS_MAX_ABS_TOLERANCE;
    printf("AKV_LOGITS_RECORDS=%u\n", logits.records);
    printf("AKV_LOGITS_MAX_ABS=%.9g\n", logits.max_abs);
    printf("AKV_LOGITS_MAX_REL=%.9g\n", logits.max_rel);
    printf("AKV_LOGITS_MAX_ABS_TOLERANCE=%.9g\n",
           (double) AKV_LOGITS_MAX_ABS_TOLERANCE);
    printf("AKV_LOGITS_TOP1_EQUAL=%d\n", logits.valid && logits.top1_equal);
    printf("AKV_TOKEN_OUTPUT_EQUAL=%d\n", text_equal);
    printf("LLAMA_GUEST_EXIT=%d\n", passed ? 0 : 1);
    free(rvv.output);
    free(akv.output);
    fflush(NULL);
    sync();
    reboot(RB_POWER_OFF);
    for (;;) {
        pause();
    }
}
