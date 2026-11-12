#include <stdint.h>
#define EXP2F_TABLE_BITS 5
#define TOINT_INTRINSICS 0
#define WANT_ERRNO_UFLOW 0
#define attribute_hidden
#ifndef __glibc_unlikely
#define __glibc_unlikely(x) __builtin_expect(!!(x), 0)
#endif
static inline uint32_t asuint(float f)
{
    union { float f; uint32_t u; } v = { .f = f };
    return v.u;
}
static inline uint64_t asuint64(double f)
{
    union { double f; uint64_t u; } v = { .f = f };
    return v.u;
}
static inline double asdouble(uint64_t u)
{
    union { double f; uint64_t u; } v = { .u = u };
    return v.f;
}
static inline float __math_uflowf(uint32_t unused)
{
    volatile float v = 0x1p-95f;
    (void)unused;
    return v * v;
}
static inline float __math_oflowf(uint32_t unused)
{
    volatile float v = 0x1p97f;
    (void)unused;
    return v * v;
}
extern const struct exp2f_data {
    uint64_t tab[1 << EXP2F_TABLE_BITS];
    double shift_scaled;
    double poly[3];
    double shift;
    double invln2_scaled;
    double poly_scaled[3];
} __exp2f_data;
