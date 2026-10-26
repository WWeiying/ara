#include "software/akv/experimental/quantized_kv/grouped_pv.h"

/* Reuse the independent division oracle against the actual SDK predicate. */
#define AKV_PV_STRIDE_CHECK_CANDIDATE_H
#define akv_pv_stride_exceeds akv_grouped_pv_stride_exceeds
#include "check.c"
