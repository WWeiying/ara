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

#define OUTPUT_CAPACITY 8192
#ifndef QBS_MODEL_PATH
#define QBS_MODEL_PATH "/model/models/qwen2.5-1.5b-instruct-q4_k_m.gguf"
#endif
#ifndef QBS_TOKEN_COUNT
#define QBS_TOKEN_COUNT "2"
#endif
#ifndef QBS_PROMPT_TEXT
#define QBS_PROMPT_TEXT "The quick brown fox jumps over the lazy dog."
#endif
#ifndef QBS_RUN_MODE
#define QBS_RUN_MODE "compare"
#endif
#ifndef QBS_REQUIRE_EQUAL
#define QBS_REQUIRE_EQUAL 1
#endif
#ifndef QBS_FORMATS
#define QBS_FORMATS ""
#endif
#ifndef QBS_TEACHER_FORCE
#define QBS_TEACHER_FORCE 0
#endif

#define LOGITS_DUMP_MAGIC 0x5142534cU
#define RVV_LOGITS_PATH "/rvv-logits.bin"
#define QBS_LOGITS_PATH "/qbs-logits.bin"

struct logits_dump_record {
  uint32_t magic;
  uint32_t version;
  uint32_t step;
  uint32_t n_vocab;
  int32_t target_token;
  uint32_t reserved;
};

struct run_result {
  int exit_code;
  size_t output_size;
  char output[OUTPUT_CAPACITY];
};

static int wait_for_device(const char *path) {
  for (int retry = 0; retry < 100; ++retry) {
    if (access(path, F_OK) == 0) return 0;
    usleep(100000);
  }
  fprintf(stderr, "device timeout: %s\n", path);
  return -1;
}

static struct run_result run_variant(const char *label, int native_qbs) {
  struct run_result result = {.exit_code = 127, .output_size = 0};
  const char *logits_path = native_qbs ? QBS_LOGITS_PATH : RVV_LOGITS_PATH;
  int output_pipe[2];
  unlink(logits_path);
  if (pipe(output_pipe) != 0) {
    perror("pipe");
    return result;
  }

  printf("QBS_TOKEN_RUN_BEGIN=%s\n", label);
  fflush(stdout);

  const pid_t child = fork();
  if (child == 0) {
    close(output_pipe[0]);
    if (dup2(output_pipe[1], STDOUT_FILENO) < 0) {
      perror("dup2");
      _exit(126);
    }
    close(output_pipe[1]);

    setenv("GGML_RISCV_REPACK_TRACE", "1", 1);
    unsetenv("GGML_RISCV_QBS");
    unsetenv("GGML_RISCV_QBS_EMULATE");
    unsetenv("GGML_RISCV_QBS_TRACE");
    unsetenv("GGML_RISCV_QBS_FORMATS");
    setenv("LLAMA_SIMPLE_LOGITS_FILE", logits_path, 1);
    if (QBS_TEACHER_FORCE) {
      setenv("LLAMA_SIMPLE_TEACHER_FORCE", "1", 1);
    } else {
      unsetenv("LLAMA_SIMPLE_TEACHER_FORCE");
    }
    if (native_qbs) {
      setenv("GGML_RISCV_QBS", "1", 1);
      setenv("GGML_RISCV_QBS_TRACE", "1", 1);
      if (QBS_FORMATS[0] != '\0') {
        setenv("GGML_RISCV_QBS_FORMATS", QBS_FORMATS, 1);
      }
    }

    execl("/run/llama-simple", "/run/llama-simple", "-m",
          QBS_MODEL_PATH, "-n", QBS_TOKEN_COUNT,
          "-ngl", "0", QBS_PROMPT_TEXT,
          NULL);
    perror("exec llama-simple");
    _exit(127);
  }

  close(output_pipe[1]);
  if (child < 0) {
    perror("fork");
    close(output_pipe[0]);
    return result;
  }

  while (result.output_size < sizeof(result.output)) {
    const ssize_t count =
        read(output_pipe[0], result.output + result.output_size,
             sizeof(result.output) - result.output_size);
    if (count > 0) {
      result.output_size += (size_t)count;
    } else if (count == 0) {
      break;
    } else if (errno != EINTR) {
      perror("read child output");
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

  printf("QBS_TOKEN_RUN_EXIT=%s:%d\n", label, result.exit_code);
  printf("QBS_TOKEN_OUTPUT_BEGIN=%s\n", label);
  fwrite(result.output, 1, result.output_size, stdout);
  if (result.output_size == 0 || result.output[result.output_size - 1] != '\n') {
    putchar('\n');
  }
  printf("QBS_TOKEN_OUTPUT_END=%s\n", label);
  fflush(stdout);
  return result;
}

static int read_logits_record(FILE *file, struct logits_dump_record *record,
                              float **values, size_t *capacity) {
  const size_t count = fread(record, sizeof(*record), 1, file);
  if (count == 0 && feof(file)) return 0;
  if (count != 1 || record->magic != LOGITS_DUMP_MAGIC ||
      record->version != 2 || record->n_vocab < 2) {
    return -1;
  }
  if (*capacity < record->n_vocab) {
    float *replacement = realloc(*values, record->n_vocab * sizeof(float));
    if (replacement == NULL) return -1;
    *values = replacement;
    *capacity = record->n_vocab;
  }
  return fread(*values, sizeof(float), record->n_vocab, file) ==
                 record->n_vocab
             ? 1
             : -1;
}

static void find_top2(const float *values, uint32_t count,
                      uint32_t *top1, uint32_t *top2) {
  *top1 = values[1] > values[0] ? 1 : 0;
  *top2 = *top1 == 0 ? 1 : 0;
  for (uint32_t index = 2; index < count; ++index) {
    if (values[index] > values[*top1]) {
      *top2 = *top1;
      *top1 = index;
    } else if (values[index] > values[*top2]) {
      *top2 = index;
    }
  }
}

static void find_top5(const float *values, uint32_t count, uint32_t top[5]) {
  for (int rank = 0; rank < 5; ++rank) top[rank] = UINT32_MAX;
  for (uint32_t index = 0; index < count; ++index) {
    for (int rank = 0; rank < 5; ++rank) {
      if (top[rank] == UINT32_MAX || values[index] > values[top[rank]]) {
        for (int move = 4; move > rank; --move) top[move] = top[move - 1];
        top[rank] = index;
        break;
      }
    }
  }
}

static unsigned top5_intersection(const uint32_t lhs[5],
                                  const uint32_t rhs[5]) {
  unsigned matches = 0;
  for (int left = 0; left < 5; ++left) {
    for (int right = 0; right < 5; ++right) {
      if (lhs[left] == rhs[right]) {
        ++matches;
        break;
      }
    }
  }
  return matches;
}

static double logits_logsumexp(const float *values, uint32_t count) {
  double maximum = values[0];
  for (uint32_t index = 1; index < count; ++index) {
    if (values[index] > maximum) maximum = values[index];
  }
  double sum = 0.0;
  for (uint32_t index = 0; index < count; ++index) {
    sum += exp((double)values[index] - maximum);
  }
  return maximum + log(sum);
}

static int compare_logits(void) {
  FILE *rvv_file = fopen(RVV_LOGITS_PATH, "rb");
  FILE *qbs_file = fopen(QBS_LOGITS_PATH, "rb");
  if (rvv_file == NULL || qbs_file == NULL) {
    perror("open logits dump");
    if (rvv_file != NULL) fclose(rvv_file);
    if (qbs_file != NULL) fclose(qbs_file);
    return -1;
  }

  float *rvv_values = NULL;
  float *qbs_values = NULL;
  size_t rvv_capacity = 0;
  size_t qbs_capacity = 0;
  unsigned records = 0;
  unsigned target_records = 0;
  unsigned top1_matches = 0;
  int common_input = 1;
  int result = 0;
  double total_kl = 0.0;
  double total_rmse = 0.0;
  double total_top5_overlap = 0.0;
  double total_rvv_nll = 0.0;
  double total_qbs_nll = 0.0;
  double global_max_abs = 0.0;
  for (;;) {
    struct logits_dump_record rvv_record;
    struct logits_dump_record qbs_record;
    const int rvv_status = read_logits_record(
        rvv_file, &rvv_record, &rvv_values, &rvv_capacity);
    const int qbs_status = read_logits_record(
        qbs_file, &qbs_record, &qbs_values, &qbs_capacity);
    if (rvv_status == 0 && qbs_status == 0) break;
    if (rvv_status != 1 || qbs_status != 1 ||
        rvv_record.step != qbs_record.step ||
        rvv_record.n_vocab != qbs_record.n_vocab ||
        rvv_record.target_token != qbs_record.target_token) {
      result = -1;
      break;
    }

    double squared_error = 0.0;
    double mean_abs = 0.0;
    double max_abs = 0.0;
    uint32_t max_index = 0;
    for (uint32_t index = 0; index < rvv_record.n_vocab; ++index) {
      const double error = fabs((double)rvv_values[index] - qbs_values[index]);
      squared_error += error * error;
      mean_abs += error;
      if (error > max_abs) {
        max_abs = error;
        max_index = index;
      }
    }
    uint32_t rvv_top1;
    uint32_t rvv_top2;
    uint32_t qbs_top1;
    uint32_t qbs_top2;
    find_top2(rvv_values, rvv_record.n_vocab, &rvv_top1, &rvv_top2);
    find_top2(qbs_values, qbs_record.n_vocab, &qbs_top1, &qbs_top2);
    const int top_equal = rvv_top1 == qbs_top1;
    uint32_t rvv_top5[5];
    uint32_t qbs_top5[5];
    find_top5(rvv_values, rvv_record.n_vocab, rvv_top5);
    find_top5(qbs_values, qbs_record.n_vocab, qbs_top5);
    const unsigned top5_common = top5_intersection(rvv_top5, qbs_top5);
    const double rvv_logsum = logits_logsumexp(rvv_values, rvv_record.n_vocab);
    const double qbs_logsum = logits_logsumexp(qbs_values, qbs_record.n_vocab);
    double kl_rvv_qbs = 0.0;
    for (uint32_t index = 0; index < rvv_record.n_vocab; ++index) {
      const double log_p = (double)rvv_values[index] - rvv_logsum;
      const double log_q = (double)qbs_values[index] - qbs_logsum;
      const double probability = exp(log_p);
      kl_rvv_qbs += probability * (log_p - log_q);
    }
    if (kl_rvv_qbs < 0.0 && kl_rvv_qbs > -1e-12) kl_rvv_qbs = 0.0;
    const int has_target = rvv_record.target_token >= 0 &&
                           (uint32_t)rvv_record.target_token < rvv_record.n_vocab;
    const double rvv_nll = has_target
                               ? rvv_logsum - rvv_values[rvv_record.target_token]
                               : NAN;
    const double qbs_nll = has_target
                               ? qbs_logsum - qbs_values[qbs_record.target_token]
                               : NAN;
    const double record_rmse = sqrt(squared_error / rvv_record.n_vocab);
    printf("QBS_LOGITS_COMPARE step=%u common_input=%d "
           "max_abs=%.9g max_index=%u mean_abs=%.9g rmse=%.9g "
           "rvv_top1=%u rvv_logit=%.9g rvv_margin=%.9g "
           "qbs_top1=%u qbs_logit=%.9g qbs_margin=%.9g top_equal=%d "
           "top5_common=%u kl_rvv_qbs=%.9g target=%d "
           "rvv_nll=%.9g qbs_nll=%.9g\n",
           rvv_record.step, common_input, max_abs, max_index,
           mean_abs / rvv_record.n_vocab,
           record_rmse,
           rvv_top1, rvv_values[rvv_top1],
           rvv_values[rvv_top1] - rvv_values[rvv_top2],
           qbs_top1, qbs_values[qbs_top1],
           qbs_values[qbs_top1] - qbs_values[qbs_top2], top_equal,
           top5_common, kl_rvv_qbs, rvv_record.target_token,
           rvv_nll, qbs_nll);
    top1_matches += top_equal;
    total_top5_overlap += top5_common / 5.0;
    total_kl += kl_rvv_qbs;
    total_rmse += record_rmse;
    if (max_abs > global_max_abs) global_max_abs = max_abs;
    if (has_target) {
      ++target_records;
      total_rvv_nll += rvv_nll;
      total_qbs_nll += qbs_nll;
    }
    ++records;
    if (!QBS_TEACHER_FORCE && common_input && !top_equal) common_input = 0;
  }
  printf("QBS_LOGITS_RECORDS=%u status=%s\n", records,
         result == 0 ? "OK" : "ERROR");
  if (result == 0 && records != 0) {
    const double rvv_ppl = target_records != 0
                               ? exp(total_rvv_nll / target_records)
                               : NAN;
    const double qbs_ppl = target_records != 0
                               ? exp(total_qbs_nll / target_records)
                               : NAN;
    printf("QBS_MODEL_METRICS records=%u target_records=%u "
           "rvv_ppl=%.9g qbs_ppl=%.9g ppl_ratio=%.9g "
           "mean_kl=%.9g top1_agreement=%.9g top5_overlap=%.9g "
           "mean_rmse=%.9g max_abs=%.9g\n",
           records, target_records, rvv_ppl, qbs_ppl, qbs_ppl / rvv_ppl,
           total_kl / records, (double)top1_matches / records,
           total_top5_overlap / records, total_rmse / records,
           global_max_abs);
  }

  free(rvv_values);
  free(qbs_values);
  fclose(rvv_file);
  fclose(qbs_file);
  return result;
}

int main(void) {
  if (mount("devtmpfs", "/dev", "devtmpfs", 0, NULL) != 0) {
    perror("mount devtmpfs");
    return 1;
  }
  if (wait_for_device("/dev/vda") != 0 ||
      wait_for_device("/dev/vdb") != 0) {
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

  int guest_ok = 0;
  if (strcmp(QBS_RUN_MODE, "native-only") == 0) {
    const struct run_result qbs = run_variant("QBS_NATIVE", 1);
    guest_ok = qbs.exit_code == 0;
    printf("QBS_TOKEN_OUTPUT_EQUAL=NA\n");
  } else {
    const struct run_result rvv = run_variant("RVV", 0);
    const struct run_result qbs = run_variant("QBS_NATIVE", 1);
    const int equal = rvv.exit_code == 0 && qbs.exit_code == 0 &&
                      rvv.output_size == qbs.output_size &&
                      memcmp(rvv.output, qbs.output, rvv.output_size) == 0;
    const int logits_ok = compare_logits() == 0;
    printf("QBS_TOKEN_OUTPUT_EQUAL=%d\n", equal);
    guest_ok = rvv.exit_code == 0 && qbs.exit_code == 0 && logits_ok &&
               (!QBS_REQUIRE_EQUAL || equal);
  }
  printf("LLAMA_GUEST_EXIT=%d\n", guest_ok ? 0 : 1);
  fflush(NULL);
  sync();
  reboot(RB_POWER_OFF);
  for (;;) pause();
}
