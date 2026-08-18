#define BENCH_CASE_ID "decode_attn_q_probe"
#define BENCH_K 1536
#define BENCH_ROWS 32
#define BENCH_INPUTS 1
#define BENCH_WEIGHT_Q4 1
#define BENCH_ATOL 2.0e-3f
#define BENCH_RTOL 2.0e-3f
#include "../llama_qwen25_real/common/benchmark_impl.h"
