#define BENCH_CASE_ID "prefill_ffn_gate_qbs"
#define BENCH_K 1536
#define BENCH_ROWS 4096
#define BENCH_INPUTS 4
#define BENCH_WEIGHT_Q4 1
#define BENCH_ATOL 2.0e-3f
#define BENCH_RTOL 2.0e-3f

#include "../llama_qwen25_real/common/qbs_benchmark_impl.h"
