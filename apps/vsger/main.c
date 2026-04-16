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

#define TOTAL_ELEMENTS 16384
#define TEST_ELEMENTS  512

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// Function prototype using vector extension
void vsger(int m, int n, const float a, const float *x, const float *y, float *A);

int main() {
    const float a = 6.66;

    vsger(128, 128, a, src1, src2, src1);
    #ifndef SPIKE
    perf_time();
    #endif

    return 0;
}


__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void vsger(int m, int n, const float a, const float *x, const float *y, float *A) {
    __asm__ volatile(
#ifndef SPIKE
        "rdcycle zero\n"
#endif
        // t6 = row stride in bytes = n * 4
        "slli t6, a1, 2\n"

        // t0 = remaining rows
        "mv t0, a0\n"
        // t1 = x pointer
        "mv t1, a2\n"
        // t2 = current A row pointer
        "mv t2, a4\n"

        "row_loop:\n"
        // ft0 = x[i]
        "flw ft0, 0(t1)\n"
        // ft1 = alpha * x[i]
        "fmul.s ft1, fa0, ft0\n"

        // reset y pointer and column counter
        "mv t3, a3\n"
        "mv t4, a1\n"
        // current A chunk pointer
        "mv t5, t2\n"

        "col_loop:\n"
        "vsetvli a5, t4, e32, m1, ta, ma\n"
        "vle32.v v0, (t3)\n"          // y chunk
        "vle32.v v1, (t5)\n"          // A row chunk
        "slli a6, a5, 2\n"
        "vfmacc.vf v1, ft1, v0\n"     // A += (alpha*x[i]) * y
        "vse32.v v1, (t5)\n"
        "add t3, t3, a6\n"
        "add t5, t5, a6\n"
        "sub t4, t4, a5\n"
        "bnez t4, col_loop\n"

        // next row
        "addi t1, t1, 4\n"
        "add t2, t2, t6\n"
        "addi t0, t0, -1\n"
        "bnez t0, row_loop\n"
        "ret\n"
    );
}
