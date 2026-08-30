#define BENCH_CASE_ID "decode_attn_q_qbs_ctx2"
#define BENCH_K 1536
#define BENCH_ROWS 64
#define BENCH_INPUTS 1
#define BENCH_WEIGHT_Q4 1
#define BENCH_ATOL 2.0e-3f
#define BENCH_RTOL 2.0e-3f
#define QBS_BENCH_ACTIVATION_CONTEXT 1
#define QBS_BENCH_CONTEXT_KEEP_VALID 1
#define QBS_BENCH_CONTEXT_GENERATION 37

#include "../llama_qwen25_real/common/qbs_benchmark_impl.h"
