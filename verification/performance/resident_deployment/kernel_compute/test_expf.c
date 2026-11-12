#include <assert.h>
#include <fenv.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

float ara_resident_expf(float x);
float ara_glibc_reference_expf(float x);

static unsigned bits(float x)
{
    unsigned u;
    memcpy(&u, &x, sizeof(u));
    return u;
}

static void check(float x)
{
    int actual_flags, expected_flags;
    float actual, expected;
    feclearexcept(FE_ALL_EXCEPT);
    actual = ara_resident_expf(x);
    actual_flags = fetestexcept(FE_ALL_EXCEPT);
    feclearexcept(FE_ALL_EXCEPT);
    expected = ara_glibc_reference_expf(x);
    expected_flags = fetestexcept(FE_ALL_EXCEPT);
    if (bits(actual) != bits(expected) || actual_flags != expected_flags) {
        fprintf(stderr, "x=%a actual=%a expected=%a flags=%x/%x\n",
                x, actual, expected, actual_flags, expected_flags);
        assert(0);
    }
}

int main(void)
{
    uint32_t seed = 1;
    assert(fesetround(FE_TONEAREST) == 0);
    for (unsigned i = 0; i <= 2000000; ++i)
        check(-110.0f * (float)i / 2000000.0f);
    for (unsigned i = 0; i < 2000000; ++i) {
        union { uint32_t u; float f; } x;
        seed = seed * 1664525u + 1013904223u;
        x.u = (seed & 0x7fffffffu) | 0x80000000u;
        if (isfinite(x.f))
            check(x.f);
    }
    check(0.0f);
    check(-0.0f);
    check(-INFINITY);
    check(-0x1.9fe368p6f);
    check(nextafterf(-0x1.9fe368p6f, -INFINITY));
    check(nextafterf(-0x1.9fe368p6f, 0.0f));
    puts("PASS: >3.9M nonpositive inputs bitwise + FP-exception match to local glibc 2.42 generic expf");
    return 0;
}
