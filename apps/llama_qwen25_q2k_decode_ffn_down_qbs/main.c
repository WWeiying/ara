#define BENCH_CASE_ID "q2k_decode_ffn_down_qbs"
#define BENCH_K 4864
#define BENCH_ROWS 8
#define BENCH_INPUTS 1
#define BENCH_WEIGHT_Q2 1
#define BENCH_ATOL 2.0e-3f
#define BENCH_RTOL 2.0e-3f

#include "../llama_qwen25_real/common/qbs_benchmark_impl.h"
