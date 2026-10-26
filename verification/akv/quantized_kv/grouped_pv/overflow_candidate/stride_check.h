#ifndef AKV_PV_STRIDE_CHECK_CANDIDATE_H
#define AKV_PV_STRIDE_CHECK_CANDIDATE_H

#include <stddef.h>

/* Candidate only. Same predicate as factor && stride > limit / factor. */
static inline int akv_pv_stride_exceeds(size_t stride, size_t factor,
                                       size_t limit) {
#if defined(__GNUC__) || defined(__clang__)
  size_t product;
  return __builtin_mul_overflow(stride, factor, &product) || product > limit;
#else
  return factor && stride > limit / factor;
#endif
}

#endif
