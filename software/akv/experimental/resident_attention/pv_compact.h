#ifndef AKV_EXPERIMENTAL_RESIDENT_PV_COMPACT_H
#define AKV_EXPERIMENTAL_RESIDENT_PV_COMPACT_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif
/* Internal admitted leaf: VLEN=1024, T=1..64, D=64/96/128, H=1/2.
 * FP16 probabilities have a 256-byte row pitch, accumulator rows 512 bytes.
 * Probability narrowing (including its fflags) has already run after softmax.
 * Other preconditions/clobbers match pv_prepared; this is not a checked API. */
void akv_experimental_resident_pv_compact(const uint16_t *probability,
    uint16_t *accumulator, const float *old_scale, uint32_t tokens,
    uint32_t dimension, uint32_t heads, uint64_t control);
#ifdef __cplusplus
}
#endif

#endif
