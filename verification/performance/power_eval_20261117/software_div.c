/* Private power-firmware workaround; single worker, benchmark FRM=RNE only. */
#include <stdint.h>
#include "softfloat.h"

_Static_assert(softfloat_flag_inexact == 1 && softfloat_flag_underflow == 2 &&
               softfloat_flag_overflow == 4 && softfloat_flag_infinite == 8 &&
               softfloat_flag_invalid == 16, "RISC-V fflags mapping");

#ifdef POWER_SOFTDIV_HOST
uint32_t power_softdiv_host_fflags;
#endif

uint32_t power_softdiv_f32_bits(uint32_t a, uint32_t b) {
    softfloat_roundingMode = softfloat_round_near_even;
    softfloat_detectTininess = softfloat_tininess_afterRounding;
    softfloat_exceptionFlags = 0;
    float32_t result = f32_div((float32_t){a}, (float32_t){b});
    unsigned flags = softfloat_exceptionFlags;
#ifdef POWER_SOFTDIV_HOST
    power_softdiv_host_fflags |= flags;
#else
    /* CSR set preserves pre-existing hardware flags and does not modify FRM. */
    __asm__ volatile("csrs fflags, %0" :: "r"(flags) : "memory");
#endif
    return result.v;
}

__attribute__((noinline))
float power_softdiv_f32_rne(float a, float b) {
    union { float f; uint32_t u; } x = {.f = a}, y = {.f = b}, z;
    z.u = power_softdiv_f32_bits(x.u, y.u);
    return z.f;
}
