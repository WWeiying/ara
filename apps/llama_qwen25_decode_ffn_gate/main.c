#define BENCH_CASE_ID "decode_ffn_gate"
#define BENCH_K 1536
#define BENCH_ROWS 8960
#define BENCH_INPUTS 1
#define BENCH_WEIGHT_Q4 1
#define BENCH_ATOL 2.0e-3f
#define BENCH_RTOL 2.0e-3f
#include "../llama_qwen25_real/common/benchmark_impl.h"
