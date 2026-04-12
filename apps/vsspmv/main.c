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
#define SPMV_ROWS 32
#define SPMV_NNZ  32

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(128), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(128), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

static uint32_t col_idx[SPMV_ROWS * SPMV_NNZ] __attribute__((aligned(128)));

void spmv_f32_32x32(const float *val, const uint32_t *col_idx,
                    const float *x, float *y);

int main() {
    for (int i = 0; i < SPMV_ROWS; ++i) {
        for (int j = 0; j < SPMV_NNZ; ++j) {
            col_idx[i * SPMV_NNZ + j] = (uint32_t)j;
        }
    }

#ifndef SPIKE
    start_timer();
#endif

    spmv_f32_32x32(src1, col_idx, src2, src2 + 64);

#ifndef SPIKE
    stop_timer();
    perf_time();
#endif

    return 0;
}


__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void spmv_f32_32x32(const float *val, const uint32_t *col_idx,
                    const float *x, float *y) {
    __asm__ volatile(
#ifndef SPIKE
        "rdcycle zero\n"
#endif
        // fixed nnz per row = 32, one full FP32 vector

        // t0 = remaining rows = 32
        "li t0, 1024\n"
        "vsetvli s0, t0, e32, m1, ta, ma\n"
        // t1 = current val row ptr
        "mv t1, a0\n"
        // t2 = current col_idx row ptr
        "mv t2, a1\n"
        // t3 = current y ptr
        "mv t3, a3\n"

        "row_loop:\n"
        // load 32 values
        "vle32.v v0, (t1)\n"

        // load 32 column indices
        "vle32.v v1, (t2)\n"

        // convert element index -> byte offset
        "vsll.vi v1, v1, 2\n"

        // gather x[col_idx]
        "vluxei32.v v2, (a2), v1\n"

        // multiply
        "vfmul.vv v3, v0, v2\n"

        // reduction seed = 0.0f
        "fmv.w.x ft0, zero\n"
        "vfmv.v.f v16, ft0\n"
        "vfredusum.vs v16, v3, v16\n"

        // store scalar y[i]
        "vfmv.f.s ft1, v16\n"
        "fsw ft1, 0(t3)\n"

        // next row
        "addi t1, t1, 128\n"     // 32 * 4
        "addi t2, t2, 128\n"     // 32 * 4
        "addi t3, t3, 4\n"
        "addi t0, t0, -32\n"
        "bnez t0, row_loop\n"

        "ret\n"
    );
}
