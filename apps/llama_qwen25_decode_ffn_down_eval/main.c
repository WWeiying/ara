#define BENCH_CASE_ID "decode_ffn_down_eval"
#define BENCH_K 8960
#define BENCH_ROWS 256
#define BENCH_INPUTS 1
#define BENCH_WEIGHT_Q4 0
#define BENCH_ATOL 2.0e-3f
#define BENCH_RTOL 2.0e-3f
#include "../llama_qwen25_real/common/benchmark_impl.h"
