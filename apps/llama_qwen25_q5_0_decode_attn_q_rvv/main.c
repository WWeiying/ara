#define BENCH_CASE_ID "q5_0_decode_attn_q_rvv"
#define BENCH_K 896
#define BENCH_ROWS 32
#define BENCH_INPUTS 1
#define BENCH_WEIGHT_Q5_0 1
#define BENCH_ATOL 2.0e-3f
#define BENCH_RTOL 2.0e-3f

#include "../llama_qwen25_real/common/benchmark_impl.h"
