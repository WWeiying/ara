#define BENCH_CASE_ID "shape_decode_n32_qbs_prebuilt"
#define BENCH_K 1536
#define BENCH_ROWS 32
#define BENCH_INPUTS 1
#define BENCH_WEIGHT_Q4 1
#define BENCH_ATOL 2.0e-3f
#define BENCH_RTOL 2.0e-3f
#define QBS_BENCH_PREBUILT_DESCRIPTOR 1

#include "../llama_qwen25_real/common/qbs_benchmark_impl.h"
