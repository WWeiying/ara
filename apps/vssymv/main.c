#include <stdint.h>
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

#define TOTAL_ELEMENTS 512
#define TEST_ELEMENTS  512

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// Function prototype using vector extension
void vssymv_f32_32x32(const float *A, const float *x, float *y,
                      const float alpha, const float beta);

int main() {
    const float a = 6.66;

    vssymv_f32_32x32(src1,src2,src1,a,a);
    #ifndef SPIKE
    perf_time();
    #endif

    return 0;
}

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void vssymv_f32_32x32(const float *A, const float *x, float *y,
                      const float alpha, const float beta) {
    __asm__ volatile(
#ifndef SPIKE
        "rdcycle zero\n"
#endif
        // 32 FP32 elements = one full vector
        "li t3, 32\n"
        "vsetvli zero, t3, e32, m1, ta, ma\n"

        // load x once
        "vle32.v v0, (a1)\n"

        // ft0 = 0.0f
        "fmv.w.x ft0, zero\n"

        // t0 = remaining rows = 32
        "li t0, 1024\n"
        // t1 = current A row ptr
        "mv t1, a0\n"
        // t2 = current y ptr
        "mv t2, a2\n"

        "row_loop:\n"
        "vsetvli s0, t0, e32, m1, ta, ma\n"
        // load one row of A
        "vle32.v v1, (t1)\n"

        // v2 = A[i,:] * x[:]
        "vfmul.vv v2, v1, v0\n"

        // reduction seed = 0
        "vfmv.v.f v16, ft0\n"
        "vfredusum.vs v16, v2, v16\n"

        // ft1 = dot(A[i,:], x)
        "vfmv.f.s ft1, v16\n"

        // ft2 = beta * y[i]
        "flw ft2, 0(t2)\n"
        "fmul.s ft2, ft2, fa1\n"

        // ft2 = alpha * dot + beta * y[i]
        "fmadd.s ft2, ft1, fa0, ft2\n"
        "fsw ft2, 0(t2)\n"

        // next row
        "addi t1, t1, 128\n"   // 32 * 4 bytes
        "addi t2, t2, 4\n"
        "sub  t0, t0, s0\n"
        "bnez t0, row_loop\n"

        "ret\n"
    );
}
