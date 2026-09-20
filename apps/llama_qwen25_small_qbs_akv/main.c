/*
 * One small, real-model replay containing both production paths. The QBS
 * benchmark is included with private FP16 helper names because the llama.cpp
 * attention operator has its own helpers with the same source names.
 */
#define BENCH_CASE_ID "shape_decode_n32_qbs"
#define BENCH_K 1536
#define BENCH_ROWS 32
#define BENCH_INPUTS 1
#define BENCH_WEIGHT_Q4 1
#define BENCH_ATOL 2.0e-3f
#define BENCH_RTOL 2.0e-3f

#define fp16_to_fp32 qbs_fp16_to_fp32
#define fp32_to_fp16 qbs_fp32_to_fp16
#define main qbs_component_main
#include "../llama_qwen25_real/common/qbs_benchmark_impl.h"
#undef main
#undef fp16_to_fp32
#undef fp32_to_fp16

#define main attention_component_main
#include "../llama_q4km_operator/main.c"
#undef main

#include "printf.h"

int main(void) {
  const int qbs_status = qbs_component_main();
  const int attention_status = attention_component_main();
  const int passed = qbs_status == 0 && attention_status == 0;
  const uint64_t qbs_cycles = benchmark_last_compute_cycles;
  const uint64_t attention_cycles = operator_last_cycles;
  const uint64_t total_cycles = qbs_cycles + attention_cycles;

#ifndef SPIKE
  printf("QBS_AKV_COMBINED result=%s qbs_cycles=%lu attention_cycles=%lu "
         "total_cycles=%lu qbs_status=%d attention_status=%d "
         "attention_mode=akv_v2\n",
         passed ? "PASS" : "FAIL", (unsigned long)qbs_cycles,
         (unsigned long)attention_cycles, (unsigned long)total_cycles,
         qbs_status, attention_status);
#else
  printstr(passed ? "QBS_AKV_COMBINED PASS\n"
                  : "QBS_AKV_COMBINED FAIL\n");
#endif
  return passed ? 0 : 1;
}
