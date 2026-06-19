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

#define TOTAL_ELEMENTS 4096

#ifndef VSTRSM_HDV_TASK_ENTRY
#define VSTRSM_HDV_TASK_ENTRY 0x80001000UL
#endif

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// Solve L * X = B (left, lower, unit-stride), 32x32 row-major FP32; B overwritten.
void strsm_f32_left_lower_32x32(const float *L, float *B);

int main() {
    strsm_f32_left_lower_32x32(src1, src2);
    return 0;
}

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void strsm_f32_left_lower_32x32(const float *L, float *B) {
    // ABI: a0=L, a1=B.
    //
    // Nested loop with a forward skip: the outer row_loop divides B[i,:] by the
    // diagonal, then (if any rows remain below) the inner update_loop does the
    // rank-1 elimination B[j,:] -= L[j][i]*X[i,:].  The forward branch target
    // update_done and both loop tops are 16B aligned EP starts.  Scalar address
    // math (slli/add) and its dependent flw are split across EPs.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16))\n"
    ".endm\n"
    ".balign 16\n"
    "vstrsm_hdv_task_start:\n"

    // setup: VL config + indices + base pointers + row count.
    "HDV_HINT 0x00\n"
    "li s0, 32\n"
    "vsetvli zero, s0, e32, m1, ta, ma\n"
    "li t0, 0\n"
    "HDV_HINT 0x0a\n"
    "mv t1, a0\n"
    "mv t2, a1\n"
    "li t6, 32\n"

    // outer loop top: diagonal address = &L[i][i].
    "row_loop:\n"
    "HDV_HINT 0x02, 0, 0, 1, 0\n"
    "slli t4, t0, 2\n"
    "add t3, t1, t4\n"
    "nop\n"
    // load the diagonal element.
    "HDV_HINT 0x00\n"
    "flw fa0, 0(t3)\n"
    "nop\n"
    "nop\n"
    // load RHS row, divide by diagonal, store back.
    "HDV_HINT 0x00\n"
    "vle32.v v0, (t2)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vfdiv.vf v0, v0, fa0\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vse32.v v0, (t2)\n"
    "nop\n"
    "nop\n"
    // set up the below-rows update: next L/B rows + remaining count.
    "HDV_HINT 0x0a\n"
    "addi t5, t1, 128\n"
    "addi a2, t2, 128\n"
    "addi a4, t6, -1\n"
    // skip the inner loop when no rows remain below.
    "HDV_HINT 0x00\n"
    "beqz a4, update_done\n"
    "nop\n"
    "nop\n"

    // inner loop top: &L[j][i] then L[j][i].
    "update_loop:\n"
    "HDV_HINT 0x00, 0, 0, 1, 0\n"
    "add a3, t5, t4\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "flw fa1, 0(a3)\n"
    "nop\n"
    "nop\n"
    // B[j,:] -= L[j][i] * X[i,:].
    "HDV_HINT 0x00\n"
    "vle32.v v1, (a2)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vfnmsac.vf v1, fa1, v0\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vse32.v v1, (a2)\n"
    "nop\n"
    "nop\n"
    // bump inner L/B pointers + decrement count.
    "HDV_HINT 0x0a\n"
    "addi t5, t5, 128\n"
    "addi a2, a2, 128\n"
    "addi a4, a4, -1\n"
    // inner back-edge.
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez a4, update_loop\n"
    "nop\n"
    "nop\n"

    // outer pointer bumps + index/row updates.
    "update_done:\n"
    "HDV_HINT 0x0a\n"
    "addi t1, t1, 128\n"
    "addi t2, t2, 128\n"
    "addi t0, t0, 1\n"
    "HDV_HINT 0x00\n"
    "addi t6, t6, -1\n"
    "nop\n"
    "nop\n"
    // outer back-edge.
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez t6, row_loop\n"
    "nop\n"
    "nop\n"

    "HDV_HINT\n"
    "ret\n"
    "nop\n"
    "nop\n"
    ".purgem HDV_HINT\n"
    ".option pop\n"
    );
}
