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

#define TOTAL_ELEMENTS 1024
#define TEST_ELEMENTS  512

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// Function prototype using vector extension
void ssyrk_f32_full_32x32x32(const float *A, float *C,
                             const float alpha, const float beta);

int main() {
    const float a = 6.66;

    ssyrk_f32_full_32x32x32(src1,src2,a,a);
    #ifndef SPIKE
    perf_time();
    #endif

    return 0;
}

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void ssyrk_f32_full_32x32x32(const float *A, float *C,
                             const float alpha, const float beta) {
    __asm__ volatile(
#ifndef SPIKE
        "rdcycle zero\n"
#endif
        // one full row = 32 FP32
        "li s0, 32\n"
        "vsetvli zero, s0, e32, m1, ta, ma\n"

        // t5 = row stride bytes = 32 * 4 = 128
        "li t5, 128\n"

        // t0 = remaining rows = 32
        "li t0, 32\n"
        // t1 = current row pointer of A
        "mv t1, a0\n"
        // t2 = current row pointer of C
        "mv t2, a1\n"

        "row_loop:\n"
        // acc = beta * C[i,:]
        "vle32.v v4, (t2)\n"
        "vfmul.vf v4, v4, fa1\n"

        // t3 = pointer to A[0][k], starting with k=0
        "mv t3, a0\n"
        // t4 = pointer to A[i][k], current row scalar stream
        "mv t4, t1\n"
        // a2 = k counter = 32
        "li a2, 32\n"

        "k_loop:\n"
        // scalar a_ik
        "flw ft0, 0(t4)\n"
        // alpha * a_ik
        "fmul.s ft1, ft0, fa0\n"

        // load column k of A: A[0][k], A[1][k], ..., A[31][k]
        "vlse32.v v0, (t3), t5\n"

        // acc += (alpha * a_ik) * A[:,k]
        "vfmacc.vf v4, ft1, v0\n"

        // next k
        "addi t3, t3, 4\n"
        "addi t4, t4, 4\n"
        "addi a2, a2, -1\n"
        "bnez a2, k_loop\n"

        // store full row C[i,:]
        "vse32.v v4, (t2)\n"

        // next row
        "addi t1, t1, 128\n"
        "addi t2, t2, 128\n"
        "addi t0, t0, -1\n"
        "bnez t0, row_loop\n"

        "ret\n"
    );
}
