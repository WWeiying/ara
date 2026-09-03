#define BENCH_CASE_ID "prefill_attn_q_qbs_m8"
#define BENCH_K 1536
#define BENCH_ROWS 1536
#define BENCH_INPUTS 8
#define BENCH_WEIGHT_Q4 1
#define BENCH_ATOL 2.0e-3f
#define BENCH_RTOL 2.0e-3f

#include "../llama_qwen25_real/common/qbs_benchmark_impl.h"
