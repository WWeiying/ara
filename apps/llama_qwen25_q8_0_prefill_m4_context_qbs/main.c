#define BENCH_CASE_ID "q8_0_prefill_m4_context_qbs"
#define BENCH_K 896
#define BENCH_ROWS 896
#define BENCH_INPUTS 4
#define BENCH_WEIGHT_Q8_0 1
#define BENCH_ATOL 2.0e-3f
#define BENCH_RTOL 2.0e-3f
#define QBS_BENCH_COMPACT_M4 1
#define QBS_BENCH_PREFLIGHT 1
#define QBS_BENCH_INDEPENDENT_ORACLE 1
#define QBS_BENCH_ACTIVATION_CONTEXT 1

#include "../llama_qwen25_real/common/qbs_benchmark_impl.h"
