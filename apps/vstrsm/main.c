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
void strsm_f32_left_lower_32x32(const float *L, float *B);

int main() {
    const float a = 6.66;

    strsm_f32_left_lower_32x32(src1, src2);
    #ifndef SPIKE
    perf_time();
    #endif

    return 0;
}

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void strsm_f32_left_lower_32x32(const float *L, float *B) {
    __asm__ volatile(
#ifndef SPIKE
        "rdcycle zero\n"
#endif
        // one full row of B = 32 FP32 = one vector
        "li s0, 32\n"
        "vsetvli zero, s0, e32, m1, ta, ma\n"

        // t0 = i
        "li t0, 0\n"
        // t1 = current row pointer of L
        "mv t1, a0\n"
        // t2 = current row pointer of B
        "mv t2, a1\n"
        // t6 = remaining rows
        "li t6, 32\n"

        "row_loop:\n"
        // diag address = &L[i][i]
        "slli t4, t0, 2\n"
        "add t3, t1, t4\n"
        "flw fa0, 0(t3)\n"            // fa0 = L[i][i]

        // load current RHS row B[i,:]
        "vle32.v v0, (t2)\n"

        // divide: X[i,:] = B[i,:] / L[i][i]
        "vfdiv.vf v0, v0, fa0\n"
        "vse32.v v0, (t2)\n"

        // update rows below:
        // B[j,:] -= L[j][i] * X[i,:]
        "addi t5, t1, 128\n"          // next row of L
        "addi a2, t2, 128\n"          // next row of B
        "addi a4, t6, -1\n"           // rows below

        "beqz a4, update_done\n"

        "update_loop:\n"
        "add a3, t5, t4\n"            // &L[j][i]
        "flw fa1, 0(a3)\n"

        "vle32.v v1, (a2)\n"
        "vfnmsac.vf v1, fa1, v0\n"    // v1 = v1 - fa1 * v0
        "vse32.v v1, (a2)\n"

        "addi t5, t5, 128\n"
        "addi a2, a2, 128\n"
        "addi a4, a4, -1\n"
        "bnez a4, update_loop\n"

        "update_done:\n"
        "addi t1, t1, 128\n"          // next L row
        "addi t2, t2, 128\n"          // next B row
        "addi t0, t0, 1\n"
        "addi t6, t6, -1\n"
        "bnez t6, row_loop\n"

        "ret\n"
    );
}
