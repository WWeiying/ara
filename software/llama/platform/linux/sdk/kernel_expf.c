/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Single-precision e^x, adapted from GNU libc 2.42 e_expf.c and e_exp2f_data.c.
 * Copyright (C) 2017-2025 Free Software Foundation, Inc.
 *
 * This library is free software; you can redistribute it and/or modify it
 * under the terms of the GNU Lesser General Public License as published by
 * the Free Software Foundation; either version 2.1, or any later version.
 * This library is distributed without any warranty, including the implied
 * warranties of merchantability or fitness for a particular purpose.
 * See <https://www.gnu.org/licenses/> for the full license text.
 *
 * Only the SDK's nonpositive softmax rescale domain is admitted. Preserve the
 * original 32-entry table, double precision reduction, cubic polynomial and
 * final F32 rounding. No errno, TLS, libc calls or alternative approximation.
 */
#include <stdint.h>

float ara_resident_expf(float x);

static const uint64_t exp_table[32] = {
    0x3ff0000000000000, 0x3fefd9b0d3158574, 0x3fefb5586cf9890f, 0x3fef9301d0125b51,
    0x3fef72b83c7d517b, 0x3fef54873168b9aa, 0x3fef387a6e756238, 0x3fef1e9df51fdee1,
    0x3fef06fe0a31b715, 0x3feef1a7373aa9cb, 0x3feedea64c123422, 0x3feece086061892d,
    0x3feebfdad5362a27, 0x3feeb42b569d4f82, 0x3feeab07dd485429, 0x3feea47eb03a5585,
    0x3feea09e667f3bcd, 0x3fee9f75e8ec5f74, 0x3feea11473eb0187, 0x3feea589994cce13,
    0x3feeace5422aa0db, 0x3feeb737b0cdc5e5, 0x3feec49182a3f090, 0x3feed503b23e255d,
    0x3feee89f995ad3ad, 0x3feeff76f2fb5e47, 0x3fef199bdd85529c, 0x3fef3720dcef9069,
    0x3fef5818dcfba487, 0x3fef7c97337b9b5f, 0x3fefa4afa2a490da, 0x3fefd0765b6e4540,
};

float ara_resident_expf(float x)
{
    union { double f; uint64_t u; } bits;
    double xd = x, kd, z, r, r2, y, s;
    uint64_t ki, t;

    if (x < -0x1.9fe368p6f) {
        /* glibc __math_uflowf(0), including its underflow/inexact flags. */
        volatile float tiny = 0x1p-95f;
        if (x == -__builtin_inff())
            return 0.0f;
        return tiny * tiny;
    }
    if (!(x <= 0.0f))
        return __builtin_nanf("");

    z = (0x1.71547652b82fep+0 * 32) * xd;
    /* TOINT_INTRINSICS=0, the generic glibc RISC-V configuration. */
    bits.f = z + 0x1.8p+52;
    ki = bits.u;
    kd = bits.f - 0x1.8p+52;
    r = z - kd;
    t = exp_table[ki % 32];
    t += ki << (52 - 5);
    bits.u = t;
    s = bits.f;
    z = (0x1.c6af84b912394p-5 / 32 / 32 / 32) * r +
        (0x1.ebfce50fac4f3p-3 / 32 / 32);
    r2 = r * r;
    y = (0x1.62e42ff0c52d6p-1 / 32) * r + 1;
    y = z * r2 + y;
    y = y * s;
    return (float)y;
}
