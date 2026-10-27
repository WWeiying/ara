#include "packed_candidate.h"

extern "C" bool m4_packed_produce(const float *x,void *y,int64_t k) {
    return m4_packed_candidate::quantize(x,y,k);
}
