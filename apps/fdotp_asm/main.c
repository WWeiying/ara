#include <stdint.h>
#include <stddef.h>
#include <string.h>

#include "runtime.h"
#include "util.h"

#ifdef SPIKE
#include <stdio.h>
#elif defined ARA_LINUX
#include <stdio.h>
#else
#include "printf.h"
#endif

#define DOTP_AVL 1024

extern double v64a[] __attribute__((aligned(32 * NR_LANES), section(".l2")));
extern double v64b[] __attribute__((aligned(32 * NR_LANES), section(".l2")));

// 64-bit dot product, hand-written RVV assembly (e64, LMUL=8).  This is the
// plain-Ara baseline; fdotp_hdv is the HDV-packetised counterpart.
double fdotp_v64b(const double *a, const double *b, size_t avl);

int main() {
    fdotp_v64b(v64a, v64b, DOTP_AVL);
    return 0;
}

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
double fdotp_v64b(const double *a, const double *b, size_t avl) {
    // ABI: a0=a, a1=b, a2=avl.  Result returned in fa0.
    // Accumulate into the vector register v24 across iterations, reduce once
    // after the loop (vfredusum) and move the scalar out (vfmv.f.s).
    __asm__ volatile (
        "vsetvli t0, a2, e64, m8, ta, ma\n"
        "vmv.v.i v24, 0\n"            // clear the vector accumulator
        "vmv.v.i v0, 0\n"            // clear the reduction seed lane
        "dotp_loop:\n"
        "vsetvli t0, a2, e64, m8, ta, ma\n"
        "vle64.v v8, (a0)\n"
        "sub a2, a2, t0\n"
        "vle64.v v16, (a1)\n"
        "slli t1, t0, 3\n"           // e64 byte stride = vl * 8
        "vfmacc.vv v24, v8, v16\n"
        "add a0, a0, t1\n"
        "add a1, a1, t1\n"
        "bnez a2, dotp_loop\n"
        "vfredusum.vs v0, v24, v0\n"
        "vfmv.f.s fa0, v0\n"
        "ret\n"
    );
}
