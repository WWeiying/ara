#define BENCH_CASE_ID "iq4_nl_decode_attn_q_qbs"
#define BENCH_K 896
#define BENCH_ROWS 32
#define BENCH_INPUTS 1
#define BENCH_WEIGHT_IQ4_NL 1
#define BENCH_ATOL 2.0e-3f
#define BENCH_RTOL 2.0e-3f

#include "../llama_qwen25_real/common/qbs_benchmark_impl.h"
