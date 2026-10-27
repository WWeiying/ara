#include "tiled_candidate.h"

extern "C" bool m4_tiled_produce(const float *x,void *y,int64_t k) {
    return m4_tiled_candidate::quantize(x,y,k);
}
