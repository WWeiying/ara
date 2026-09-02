#include <errno.h>
#include <math.h>
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

#ifndef AKV_MODEL_LOGITS_MAX_KL_TOLERANCE
#define AKV_MODEL_LOGITS_MAX_KL_TOLERANCE 0.02
#endif

#ifndef AKV_MODEL_LOGITS_MIN_COSINE_TOLERANCE
#define AKV_MODEL_LOGITS_MIN_COSINE_TOLERANCE 0.999
#endif

#ifndef AKV_MODEL_LOGITS_MIN_TOP5_OVERLAP_TOLERANCE
#define AKV_MODEL_LOGITS_MIN_TOP5_OVERLAP_TOLERANCE 0.8
#endif

#ifndef AKV_MODEL_GUEST_PATH
#define AKV_MODEL_GUEST_PATH "/model/models/qwen2.5-1.5b-instruct-q4_k_m.gguf"
#endif

#ifndef AKV_MODEL_PROMPT
#define AKV_MODEL_PROMPT "The quick brown fox jumps over the lazy dog."
#endif

#ifndef AKV_MODEL_TOKENS
#define AKV_MODEL_TOKENS "2"
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
    uint32_t comparable_records;
    float max_abs;
    float max_rel;
    double mean_abs;
    double mean_rmse;
    double mean_kl;
    double mean_cosine;
    double top5_overlap;
    double max_kl;
    double min_cosine;
    double min_top5_overlap;
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

static void find_top5(const float * values, uint32_t count, uint32_t top[5]) {
    const unsigned limit = count < 5 ? count : 5;
    for (unsigned rank = 0; rank < 5; ++rank) {
        top[rank] = UINT32_MAX;
    }
    for (uint32_t index = 0; index < count; ++index) {
        for (unsigned rank = 0; rank < limit; ++rank) {
            if (top[rank] == UINT32_MAX || values[index] > values[top[rank]]) {
                for (unsigned move = 4; move > rank; --move) {
                    top[move] = top[move - 1];
                }
                top[rank] = index;
                break;
            }
        }
    }
}

static unsigned top5_intersection(const uint32_t lhs[5],
                                  const uint32_t rhs[5], unsigned count) {
    unsigned matches = 0;
    for (unsigned left = 0; left < count; ++left) {
        for (unsigned right = 0; right < count; ++right) {
            if (lhs[left] == rhs[right]) {
                ++matches;
                break;
            }
        }
    }
    return matches;
}

static double logits_logsumexp(const float * values, uint32_t count) {
    double maximum = values[0];
    for (uint32_t index = 1; index < count; ++index) {
        if (values[index] > maximum) {
            maximum = values[index];
        }
    }
    double sum = 0.0;
    for (uint32_t index = 0; index < count; ++index) {
        sum += exp((double)values[index] - maximum);
    }
    return maximum + log(sum);
}

static struct logits_comparison compare_logits(const char * label,
                                                const char * rvv_path,
                                                const char * akv_path) {
    struct logits_comparison result = {
        .valid = 0,
        .top1_equal = 1,
        .records = 0,
        .comparable_records = 0,
        .max_abs = 0.0f,
        .max_rel = 0.0f,
        .mean_abs = 0.0,
        .mean_rmse = 0.0,
        .mean_kl = 0.0,
        .mean_cosine = 0.0,
        .top5_overlap = 0.0,
        .max_kl = 0.0,
        .min_cosine = 1.0,
        .min_top5_overlap = 1.0,
    };
    FILE * rvv_file = fopen(rvv_path, "rb");
    FILE * akv_file = fopen(akv_path, "rb");
    float * rvv_logits = NULL;
    float * akv_logits = NULL;
    int same_context = 1;

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
        float record_max_abs = 0.0f;
        float record_max_rel = 0.0f;
        uint32_t record_max_abs_index = 0;
        double absolute_sum = 0.0;
        double squared_error = 0.0;
        double dot_product = 0.0;
        double rvv_squared = 0.0;
        double akv_squared = 0.0;
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
            const double rvv_value = rvv_logits[index];
            const double akv_value = akv_logits[index];
            absolute_sum += absolute;
            squared_error += (akv_value - rvv_value) * (akv_value - rvv_value);
            dot_product += rvv_value * akv_value;
            rvv_squared += rvv_value * rvv_value;
            akv_squared += akv_value * akv_value;
            if (absolute > record_max_abs) {
                record_max_abs = absolute;
                record_max_abs_index = index;
            }
            if (relative > record_max_rel) {
                record_max_rel = relative;
            }
        }
        const double rvv_logsum = logits_logsumexp(rvv_logits, rvv_record.n_vocab);
        const double akv_logsum = logits_logsumexp(akv_logits, akv_record.n_vocab);
        double record_kl = 0.0;
        for (uint32_t index = 0; index < rvv_record.n_vocab; ++index) {
            const double log_p = (double)rvv_logits[index] - rvv_logsum;
            const double log_q = (double)akv_logits[index] - akv_logsum;
            record_kl += exp(log_p) * (log_p - log_q);
        }
        if (record_kl < 0.0 && record_kl > -1.0e-12) {
            record_kl = 0.0;
        }
        uint32_t rvv_top5[5];
        uint32_t akv_top5[5];
        find_top5(rvv_logits, rvv_record.n_vocab, rvv_top5);
        find_top5(akv_logits, akv_record.n_vocab, akv_top5);
        const double norm_product = sqrt(rvv_squared * akv_squared);
        const double record_cosine = norm_product == 0.0
            ? (rvv_squared == 0.0 && akv_squared == 0.0 ? 1.0 : 0.0)
            : dot_product / norm_product;
        const double record_mean_abs = absolute_sum / rvv_record.n_vocab;
        const double record_rmse = sqrt(squared_error / rvv_record.n_vocab);
        const unsigned top_count = rvv_record.n_vocab < 5 ? rvv_record.n_vocab : 5;
        const double record_top5_overlap =
            (double) top5_intersection(rvv_top5, akv_top5, top_count) / top_count;
        if (same_context) {
            printf("LOGITS_RECORD pair=%s step=%u target=%d top1_equal=%d "
                   "baseline_top1=%u candidate_top1=%u max_abs=%.9g "
                   "max_abs_index=%u baseline_at_max=%.9g candidate_at_max=%.9g "
                   "mean_abs=%.9g rmse=%.9g kl=%.9g cosine=%.9g "
                   "top5_overlap=%.9g\n",
                   label, rvv_record.step, rvv_record.target_token,
                   rvv_top == akv_top, rvv_top, akv_top, record_max_abs,
                   record_max_abs_index, rvv_logits[record_max_abs_index],
                   akv_logits[record_max_abs_index], record_mean_abs,
                   record_rmse, record_kl, record_cosine,
                   record_top5_overlap);
            if (record_max_abs > result.max_abs) {
                result.max_abs = record_max_abs;
            }
            if (record_max_rel > result.max_rel) {
                result.max_rel = record_max_rel;
            }
            result.mean_abs += record_mean_abs;
            result.mean_rmse += record_rmse;
            result.mean_kl += record_kl;
            result.mean_cosine += record_cosine;
            result.top5_overlap += record_top5_overlap;
            if (record_kl > result.max_kl) {
                result.max_kl = record_kl;
            }
            if (record_cosine < result.min_cosine) {
                result.min_cosine = record_cosine;
            }
            if (record_top5_overlap < result.min_top5_overlap) {
                result.min_top5_overlap = record_top5_overlap;
            }
            ++result.comparable_records;
            if (rvv_top != akv_top) {
                result.top1_equal = 0;
                same_context = 0;
            }
        }
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
    if (result.comparable_records != 0) {
        const double denominator = result.comparable_records;
        result.mean_abs /= denominator;
        result.mean_rmse /= denominator;
        result.mean_kl /= denominator;
        result.mean_cosine /= denominator;
        result.top5_overlap /= denominator;
    }
    return result;
}

static int model_quality_pass(const struct logits_comparison * comparison) {
    return comparison->valid && comparison->records > 0 &&
           comparison->comparable_records == comparison->records &&
           comparison->top1_equal &&
           comparison->max_kl <= AKV_MODEL_LOGITS_MAX_KL_TOLERANCE &&
           comparison->min_cosine >= AKV_MODEL_LOGITS_MIN_COSINE_TOLERANCE &&
           comparison->min_top5_overlap >=
               AKV_MODEL_LOGITS_MIN_TOP5_OVERLAP_TOLERANCE;
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

static struct run_result run_variant(const char * label,
                                     const char * logits_path,
                                     int enable_qbs,
                                     const char * akv_kernel,
                                     int enable_trace,
                                     int qbs_cross_op_context) {
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
        unsetenv("GGML_RISCV_QBS_TRACE_CALLS");
        unsetenv("GGML_RISCV_QBS_TRACE_LIFETIME");
        unsetenv("GGML_RISCV_QBS_CROSS_OP_CONTEXT");
        unsetenv("GGML_RISCV_MODEL_TRACE");
        unsetenv("GGML_RISCV_AKV");
        unsetenv("GGML_RISCV_AKV_EMULATE");
        unsetenv("GGML_RISCV_AKV_KERNEL");
        unsetenv("GGML_RISCV_AKV_TRACE");
        if (enable_qbs) {
            setenv("GGML_RISCV_QBS", "1", 1);
            if (qbs_cross_op_context >= 0) {
                setenv("GGML_RISCV_QBS_CROSS_OP_CONTEXT",
                       qbs_cross_op_context ? "1" : "0", 1);
            }
        }
        if (enable_trace) {
            if (enable_qbs) {
                setenv("GGML_RISCV_QBS_TRACE", "1", 1);
                setenv("GGML_RISCV_QBS_TRACE_CALLS", "1", 1);
#if defined(AKV_MODEL_QBS_LIFETIME)
                setenv("GGML_RISCV_QBS_TRACE_LIFETIME", "1", 1);
#endif
            }
            setenv("GGML_RISCV_MODEL_TRACE", "1", 1);
            setenv("GGML_RISCV_AKV_TRACE", "1", 1);
        }
        if (akv_kernel != NULL) {
            setenv("GGML_RISCV_AKV_EMULATE", "1", 1);
            setenv("GGML_RISCV_AKV_KERNEL", akv_kernel, 1);
        }
        setenv("LLAMA_SIMPLE_LOGITS_FILE", logits_path, 1);

        execl("/run/llama-simple", "/run/llama-simple",
              "-m", AKV_MODEL_GUEST_PATH,
              "-n", AKV_MODEL_TOKENS, "-ngl", "0", "-t", "1",
              "-tb", "1", "-fa", "on", AKV_MODEL_PROMPT, NULL);
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

static int output_equal(const struct run_result * lhs,
                        const struct run_result * rhs) {
    return !lhs->capture_failed && !rhs->capture_failed &&
           lhs->exit_code == 0 && rhs->exit_code == 0 &&
           lhs->output_size == rhs->output_size &&
           (lhs->output_size == 0 ||
            memcmp(lhs->output, rhs->output, lhs->output_size) == 0);
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
    unlink("/qbs.logits");
    unlink("/optimized.logits");
#if defined(AKV_MODEL_QBS_LIFETIME)
    const struct run_result baseline =
        run_variant("QBS_CONTEXT_BASELINE", "/qbs-baseline.logits",
                    1, NULL, 1, 0);
    const struct run_result optimized =
        run_variant("QBS_CROSS_OP", "/qbs-cross-op.logits",
                    1, NULL, 1, 1);
    const struct logits_comparison comparison =
        compare_logits("QBS_CROSS_OP", "/qbs-baseline.logits",
                       "/qbs-cross-op.logits");
    const int text_equal = output_equal(&baseline, &optimized);
    const int passed = baseline.exit_code == 0 && optimized.exit_code == 0 &&
                       comparison.valid && comparison.comparable_records > 0 &&
                       comparison.top1_equal &&
                       comparison.max_abs <= AKV_LOGITS_MAX_ABS_TOLERANCE &&
                       text_equal;

    printf("QBS_CROSS_OP_LOGITS_RECORDS=%u\n", comparison.records);
    printf("QBS_CROSS_OP_LOGITS_COMPARABLE_RECORDS=%u\n",
           comparison.comparable_records);
    printf("QBS_CROSS_OP_LOGITS_MAX_ABS=%.9g\n", comparison.max_abs);
    printf("QBS_CROSS_OP_LOGITS_MAX_REL=%.9g\n", comparison.max_rel);
    printf("QBS_CROSS_OP_LOGITS_TOP1_EQUAL=%d\n",
           comparison.valid && comparison.top1_equal);
    printf("QBS_CROSS_OP_TOKEN_OUTPUT_EQUAL=%d\n", text_equal);
    printf("LLAMA_GUEST_EXIT=%d\n", passed ? 0 : 1);
    free(baseline.output);
    free(optimized.output);
#else
    const struct run_result rvv =
        run_variant("RVV", "/rvv.logits", 0, NULL, 0, -1);
#if defined(AKV_MODEL_QBS_AKV_V2)
    const struct run_result qbs =
        run_variant("QBS_ONLY", "/qbs.logits", 1, NULL, 0, -1);
    const struct run_result optimized =
        run_variant("QBS_AKV_V2", "/optimized.logits", 1, "v2", 1, -1);
    const struct logits_comparison qbs_rvv_logits =
        compare_logits("QBS_RVV", "/rvv.logits", "/qbs.logits");
    const struct logits_comparison akv_logits =
        compare_logits("AKV", "/qbs.logits", "/optimized.logits");
    const int qbs_rvv_text_equal = output_equal(&rvv, &qbs);
    const int akv_text_equal = output_equal(&qbs, &optimized);
    const int passed = rvv.exit_code == 0 && qbs.exit_code == 0 &&
                       optimized.exit_code == 0 && qbs_rvv_text_equal &&
                       akv_text_equal && model_quality_pass(&qbs_rvv_logits) &&
                       model_quality_pass(&akv_logits);

    printf("QBS_RVV_LOGITS_RECORDS=%u\n", qbs_rvv_logits.records);
    printf("QBS_RVV_LOGITS_COMPARABLE_RECORDS=%u\n",
           qbs_rvv_logits.comparable_records);
    printf("QBS_RVV_LOGITS_MAX_ABS=%.9g\n", qbs_rvv_logits.max_abs);
    printf("QBS_RVV_LOGITS_MAX_REL=%.9g\n", qbs_rvv_logits.max_rel);
    printf("QBS_RVV_LOGITS_MEAN_ABS=%.9g\n", qbs_rvv_logits.mean_abs);
    printf("QBS_RVV_LOGITS_MEAN_RMSE=%.9g\n", qbs_rvv_logits.mean_rmse);
    printf("QBS_RVV_LOGITS_MEAN_KL=%.9g\n", qbs_rvv_logits.mean_kl);
    printf("QBS_RVV_LOGITS_MEAN_COSINE=%.9g\n", qbs_rvv_logits.mean_cosine);
    printf("QBS_RVV_LOGITS_TOP5_OVERLAP=%.9g\n", qbs_rvv_logits.top5_overlap);
    printf("QBS_RVV_LOGITS_MAX_KL=%.9g\n", qbs_rvv_logits.max_kl);
    printf("QBS_RVV_LOGITS_MIN_COSINE=%.9g\n", qbs_rvv_logits.min_cosine);
    printf("QBS_RVV_LOGITS_MIN_TOP5_OVERLAP=%.9g\n",
           qbs_rvv_logits.min_top5_overlap);
    printf("QBS_RVV_LOGITS_TOP1_EQUAL=%d\n",
           qbs_rvv_logits.valid && qbs_rvv_logits.top1_equal);
    printf("QBS_RVV_TOKEN_OUTPUT_EQUAL=%d\n", qbs_rvv_text_equal);
    printf("AKV_LOGITS_RECORDS=%u\n", akv_logits.records);
    printf("AKV_LOGITS_COMPARABLE_RECORDS=%u\n",
           akv_logits.comparable_records);
    printf("AKV_LOGITS_MAX_ABS=%.9g\n", akv_logits.max_abs);
    printf("AKV_LOGITS_MAX_REL=%.9g\n", akv_logits.max_rel);
    printf("AKV_LOGITS_MEAN_ABS=%.9g\n", akv_logits.mean_abs);
    printf("AKV_LOGITS_MEAN_RMSE=%.9g\n", akv_logits.mean_rmse);
    printf("AKV_LOGITS_MEAN_KL=%.9g\n", akv_logits.mean_kl);
    printf("AKV_LOGITS_MEAN_COSINE=%.9g\n", akv_logits.mean_cosine);
    printf("AKV_LOGITS_TOP5_OVERLAP=%.9g\n", akv_logits.top5_overlap);
    printf("AKV_LOGITS_MAX_KL=%.9g\n", akv_logits.max_kl);
    printf("AKV_LOGITS_MIN_COSINE=%.9g\n", akv_logits.min_cosine);
    printf("AKV_LOGITS_MIN_TOP5_OVERLAP=%.9g\n",
           akv_logits.min_top5_overlap);
    printf("AKV_LOGITS_MAX_ABS_TOLERANCE=%.9g\n",
           (double) AKV_LOGITS_MAX_ABS_TOLERANCE);
    printf("MODEL_LOGITS_MAX_KL_TOLERANCE=%.9g\n",
           (double) AKV_MODEL_LOGITS_MAX_KL_TOLERANCE);
    printf("MODEL_LOGITS_MIN_COSINE_TOLERANCE=%.9g\n",
           (double) AKV_MODEL_LOGITS_MIN_COSINE_TOLERANCE);
    printf("MODEL_LOGITS_MIN_TOP5_OVERLAP_TOLERANCE=%.9g\n",
           (double) AKV_MODEL_LOGITS_MIN_TOP5_OVERLAP_TOLERANCE);
    printf("MODEL_NUMERICAL_CONTRACT=decision-preserving-v1\n");
    printf("AKV_LOGITS_TOP1_EQUAL=%d\n",
           akv_logits.valid && akv_logits.top1_equal);
    printf("AKV_TOKEN_OUTPUT_EQUAL=%d\n", akv_text_equal);
    printf("LLAMA_GUEST_EXIT=%d\n", passed ? 0 : 1);
    free(qbs.output);
    free(optimized.output);
#else
    const struct run_result akv =
        run_variant("AKV_V1_EMULATE", "/optimized.logits", 0, "v1", 1, -1);
    const struct logits_comparison akv_logits =
        compare_logits("AKV", "/rvv.logits", "/optimized.logits");
    const int akv_text_equal = output_equal(&rvv, &akv);
    const int passed = akv_text_equal && akv_logits.valid &&
                       akv_logits.top1_equal &&
                       akv_logits.max_abs <= AKV_LOGITS_MAX_ABS_TOLERANCE;

    printf("AKV_LOGITS_RECORDS=%u\n", akv_logits.records);
    printf("AKV_LOGITS_COMPARABLE_RECORDS=%u\n",
           akv_logits.comparable_records);
    printf("AKV_LOGITS_MAX_ABS=%.9g\n", akv_logits.max_abs);
    printf("AKV_LOGITS_MAX_REL=%.9g\n", akv_logits.max_rel);
    printf("AKV_LOGITS_MEAN_ABS=%.9g\n", akv_logits.mean_abs);
    printf("AKV_LOGITS_MEAN_RMSE=%.9g\n", akv_logits.mean_rmse);
    printf("AKV_LOGITS_MEAN_KL=%.9g\n", akv_logits.mean_kl);
    printf("AKV_LOGITS_MEAN_COSINE=%.9g\n", akv_logits.mean_cosine);
    printf("AKV_LOGITS_TOP5_OVERLAP=%.9g\n", akv_logits.top5_overlap);
    printf("AKV_LOGITS_MAX_ABS_TOLERANCE=%.9g\n",
           (double) AKV_LOGITS_MAX_ABS_TOLERANCE);
    printf("AKV_LOGITS_TOP1_EQUAL=%d\n",
           akv_logits.valid && akv_logits.top1_equal);
    printf("AKV_TOKEN_OUTPUT_EQUAL=%d\n", akv_text_equal);
    printf("LLAMA_GUEST_EXIT=%d\n", passed ? 0 : 1);
    free(akv.output);
#endif
    free(rvv.output);
#endif
    fflush(NULL);
    sync();
    reboot(RB_POWER_OFF);
    for (;;) {
        pause();
    }
}
