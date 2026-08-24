#define BENCH_CASE_ID "q3k_decode_attn_q_qbs"
#define BENCH_K 1536
#define BENCH_ROWS 256
#define BENCH_INPUTS 1
#define BENCH_WEIGHT_Q3 1
#define BENCH_ATOL 2.0e-3f
#define BENCH_RTOL 2.0e-3f

#include "../llama_qwen25_real/common/qbs_benchmark_impl.h"
