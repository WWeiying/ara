#define BENCH_CASE_ID "shape_prefill_n256_qbs"
#define BENCH_K 1536
#define BENCH_ROWS 256
#define BENCH_INPUTS 4
#define BENCH_WEIGHT_Q4 1
#define BENCH_ATOL 2.0e-3f
#define BENCH_RTOL 2.0e-3f

#include "../llama_qwen25_real/common/qbs_benchmark_impl.h"
