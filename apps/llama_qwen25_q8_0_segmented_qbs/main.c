#define BENCH_CASE_ID "q8_0_segmented_qbs"
#define BENCH_K 896
#define BENCH_ROWS 33
#define BENCH_INPUTS 3
#define BENCH_WEIGHT_Q8_0 1
#define BENCH_ATOL 2.0e-3f
#define BENCH_RTOL 2.0e-3f
#define main original_benchmark_main
#include "../llama_qwen25_real/common/qbs_benchmark_impl.h"
#undef main

extern const unsigned char segment_source_weights_start[];
static unsigned char segment_weights[36 * BENCH_BLOCKS * 34]
    __attribute__((aligned(64)));
static unsigned char work[4096] __attribute__((aligned(64)));
static float original[BENCH_OUTPUTS];

static uint32_t flags(void) {
  uint32_t result;
  asm volatile("csrr %0, fflags" : "=r"(result));
  return result;
}

int main(void) {
  qbs_device_t device;
  if (qbs_device_query(qbs_native_info, NULL, &device) != QBS_STATUS_OK) return 1;
  benchmark_quantize();
  const qbs_problem_t problem = {
      .weight_profile = QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,
      .activation_profile = QBS_ACTIVATION_PROFILE_Q8_0,
      .weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
      .activation_storage = QBS_ACTIVATION_STORAGE_ROW_MAJOR,
      .m = BENCH_INPUTS, .n = BENCH_ROWS, .k_elements = BENCH_K,
  };
  const unsigned segments[] = {16, 3};
  for (unsigned test = 0; test < 2; ++test) {
    const unsigned segment = segments[test];
    // This forced smaller software K limit exercises split-K using the exact
    // short real capture; it is not a native long-K model performance claim.
    qbs_device_t limited = device;
    limited.capabilities.max_k_blocks = segment;
    qbs_plan_t before, after;
    if (qbs_plan_create(&limited, &problem, &before) != QBS_STATUS_OK ||
        qbs_plan_create_segmented_r4(&limited, &problem, segment, &after) != QBS_STATUS_OK ||
        before.workspace_bytes > sizeof(work) || after.workspace_bytes > sizeof(work)) return 2;
    if (qbs_repack_weight_r4_segmented(problem.weight_profile,
        segment_source_weights_start, BENCH_ROWS * BENCH_BLOCKS * 34,
        BENCH_ROWS, BENCH_BLOCKS, segment, segment_weights,
        sizeof(segment_weights)) != QBS_STATUS_OK) return 3;
    uint64_t cycles[2];
    uint32_t status_flags[2];
    for (unsigned mode = 0; mode < 2; ++mode) {
      const qbs_plan_t *plan = mode ? &after : &before;
      const void *weights = mode ? segment_weights : benchmark_weight_start;
      memset(benchmark_output, 0, sizeof(benchmark_output));
      asm volatile("csrw fflags, zero" ::: "memory");
      uint64_t start = benchmark_cycle();
      qbs_status_t status = qbs_execute(plan, weights, sizeof(segment_weights),
          quantized_activation, sizeof(quantized_activation), benchmark_output,
          BENCH_OUTPUTS, BENCH_ROWS, work, sizeof(work),
          qbs_native_execute_command, NULL);
      cycles[mode] = benchmark_cycle() - start;
      status_flags[mode] = flags();
      if (status != QBS_STATUS_OK) return 4;
      if (!mode) memcpy(original, benchmark_output, sizeof(original));
      else if (memcmp(original, benchmark_output, sizeof(original)) != 0) return 5;
      float max_abs, max_rel;
      uint64_t checksum;
      if (benchmark_validate(&max_abs, &max_rel, &checksum) != 0) return 6;
    }
    if (status_flags[0] != status_flags[1]) return 7;
    printf("QBS_SEGMENTED PASS segment=%u m=%u n=%u k=%u old_cycles=%lu new_cycles=%lu flags=%u exact_outputs=%u forced_split=1\n",
           segment, BENCH_INPUTS, BENCH_ROWS, BENCH_K,
           (unsigned long)cycles[0], (unsigned long)cycles[1], status_flags[0], BENCH_OUTPUTS);
  }
  return 0;
}
