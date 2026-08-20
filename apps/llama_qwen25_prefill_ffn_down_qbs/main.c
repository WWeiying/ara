#define BENCH_CASE_ID "prefill_ffn_down_qbs"
#define BENCH_K 8960
#define BENCH_ROWS 64
#define BENCH_INPUTS 4
#define BENCH_WEIGHT_Q4 0
#define BENCH_ATOL 2.0e-3f
#define BENCH_RTOL 2.0e-3f

#include "../llama_qwen25_real/common/qbs_benchmark_impl.h"
