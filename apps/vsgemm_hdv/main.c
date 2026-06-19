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

#ifndef VSGEMM_HDV_TASK_ENTRY
#define VSGEMM_HDV_TASK_ENTRY 0x80001000UL
#endif

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// C = A * B, 32x32x32 row-major FP32, 4-row register blocking.
void gemm_f32_32x32x32_4row(const float *A, const float *B, float *C);

int main() {
    gemm_f32_32x32x32_4row(src1, src2, src1);
    return 0;
}

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void gemm_f32_32x32x32_4row(const float *A, const float *B, float *C) {
    // ABI: a0=A, a1=B, a2=C.
    //
    // Nested loop, 4-row blocking: outer (row_block_loop) processes 4 C rows at a
    // time with accumulators v8..v11; inner (k_loop) loads 4 scalars A[i+r][k]
    // and one B[k,:] row, doing 4 vfmacc.vf.  Scalar loads are one-per-EP (the
    // scalar LSU is synchronous); the 4 vfmacc are packed (Ara resolves the
    // vector deps); each "addi a5,t2,off ; vse v,(a5)" store base is split.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16))\n"
    ".endm\n"
    ".balign 16\n"
    "vsgemm_hdv_task_start:\n"

    // setup: VL config + row-block count + A/C bases.
    "HDV_HINT 0x00\n"
    "li a3, 32\n"
    "vsetvli zero, a3, e32, m1, ta, ma\n"
    "li t0, 8\n"
    "HDV_HINT 0x02\n"
    "mv t1, a0\n"
    "mv t2, a2\n"
    "nop\n"

    // outer loop top: zero the 4 row accumulators.
    "row_block_loop_32:\n"
    "HDV_HINT 0x0a, 0, 0, 1, 0\n"
    "vmv.v.i v8, 0\n"
    "vmv.v.i v9, 0\n"
    "vmv.v.i v10, 0\n"
    "HDV_HINT 0x00\n"
    "vmv.v.i v11, 0\n"
    "nop\n"
    "nop\n"
    // 4 A row pointers for rows i..i+3.
    "HDV_HINT 0x0a\n"
    "mv t3, t1\n"
    "addi t4, t1, 128\n"
    "addi t5, t1, 256\n"
    "HDV_HINT 0x0a\n"
    "addi t6, t1, 384\n"
    "mv a3, a1\n"
    "li a4, 1024\n"

    // inner loop top: VL config.
    "k_loop_32:\n"
    "HDV_HINT 0x00, 0, 0, 1, 0\n"
    "vsetvli zero, a4, e32, m1, ta, ma\n"
    "nop\n"
    "nop\n"
    // 4 scalar loads A[i+r][k] (one per EP: synchronous scalar LSU).
    "HDV_HINT 0x00\n"
    "flw fa0, 0(t3)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "flw fa1, 0(t4)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "flw fa2, 0(t5)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "flw fa3, 0(t6)\n"
    "nop\n"
    "nop\n"
    // load one B[k,:] row.
    "HDV_HINT 0x00\n"
    "vle32.v v0, (a3)\n"
    "nop\n"
    "nop\n"
    // 4 fmacc into the 4 accumulators (vector chain).
    "HDV_HINT 0x0a\n"
    "vfmacc.vf v8, fa0, v0\n"
    "vfmacc.vf v9, fa1, v0\n"
    "vfmacc.vf v10, fa2, v0\n"
    "HDV_HINT 0x00\n"
    "vfmacc.vf v11, fa3, v0\n"
    "nop\n"
    "nop\n"
    // advance A row pointers (4) ...
    "HDV_HINT 0x0a\n"
    "addi t3, t3, 4\n"
    "addi t4, t4, 4\n"
    "addi t5, t5, 4\n"
    // ... B row pointer + k decrement.
    "HDV_HINT 0x0a\n"
    "addi t6, t6, 4\n"
    "addi a3, a3, 128\n"
    "addi a4, a4, -32\n"
    // inner back-edge.
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez a4, k_loop_32\n"
    "nop\n"
    "nop\n"

    // store row i.
    "HDV_HINT 0x00\n"
    "vse32.v v8, (t2)\n"
    "nop\n"
    "nop\n"
    // store row i+1.
    "HDV_HINT 0x00\n"
    "addi a5, t2, 128\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vse32.v v9, (a5)\n"
    "nop\n"
    "nop\n"
    // store row i+2.
    "HDV_HINT 0x00\n"
    "addi a5, t2, 256\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vse32.v v10, (a5)\n"
    "nop\n"
    "nop\n"
    // store row i+3.
    "HDV_HINT 0x00\n"
    "addi a5, t2, 384\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vse32.v v11, (a5)\n"
    "nop\n"
    "nop\n"
    // advance to next 4-row block + block decrement.
    "HDV_HINT 0x0a\n"
    "addi t1, t1, 512\n"
    "addi t2, t2, 512\n"
    "addi t0, t0, -1\n"
    // outer back-edge.
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez t0, row_block_loop_32\n"
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
