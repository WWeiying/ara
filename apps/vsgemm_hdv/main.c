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
void gemm_f32_64x64x64_4row(const float *A, const float *B, float *C);
void gemm_f32_128x128x128_4row(const float *A, const float *B, float *C);

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
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=1\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17))\n"
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

// C = A * B, 64x64x64 row-major FP32, 4-row register blocking.
void gemm_f32_64x64x64_4row(const float *A, const float *B, float *C);

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void gemm_f32_64x64x64_4row(const float *A, const float *B, float *C) {
    // ABI: a0=A, a1=B, a2=C.
    //
    // M=N=K=64, 4-row blocking, VL=32 -> 2 vector chunks per row.
    // Accumulators: v8/v9 (row i), v10/v11 (i+1), v12/v13 (i+2), v14/v15 (i+3).
    // Each B[k][:] row = 64 elements = 256B, loaded as 2 chunks.
    // prefetch_mode=2: N=2 chunks, stride = 256B.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=2\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17))\n"
    ".endm\n"
    ".balign 16\n"
    "vsgemm_64x64_hdv_task_start:\n"

    // setup: VL config + block count + A/C bases.
    "HDV_HINT 0x00\n"
    "li a3, 32\n"
    "vsetvli zero, a3, e32, m1, ta, ma\n"
    "li t0, 16\n"
    "HDV_HINT 0x02\n"
    "mv t1, a0\n"
    "mv t2, a2\n"
    "nop\n"

    // outer loop: zero 8 accumulators.
    "row_block_loop_64:\n"
    "HDV_HINT 0x0a, 0, 0, 1, 0\n"
    "vmv.v.i v8, 0\n"
    "vmv.v.i v9, 0\n"
    "vmv.v.i v10, 0\n"
    "HDV_HINT 0x0a\n"
    "vmv.v.i v11, 0\n"
    "vmv.v.i v12, 0\n"
    "vmv.v.i v13, 0\n"
    "HDV_HINT 0x00\n"
    "vmv.v.i v14, 0\n"
    "vmv.v.i v15, 0\n"
    "nop\n"
    // 4 A row pointers.
    "HDV_HINT 0x0a\n"
    "mv t3, t1\n"
    "addi t4, t1, 256\n"
    "addi t5, t1, 512\n"
    "HDV_HINT 0x0a\n"
    "addi t6, t1, 768\n"
    "mv a3, a1\n"
    "li a4, 2048\n"

    // inner loop: VL config.
    "k_loop_64:\n"
    "HDV_HINT 0x00, 0, 0, 1, 0\n"
    "vsetvli zero, a4, e32, m1, ta, ma\n"
    "nop\n"
    "nop\n"
    // 4 scalar loads.
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
    // load B[k][:] - 2 chunks.
    "HDV_HINT 0x0a\n"
    "vle32.v v0, (a3)\n"
    "addi a5, a3, 128\n"
    "vle32.v v1, (a5)\n"
    "nop\n"
    // 8 fmacc (4 rows x 2 chunks).
    "HDV_HINT 0x0a\n"
    "vfmacc.vf v8,  fa0, v0\n"
    "vfmacc.vf v9,  fa0, v1\n"
    "vfmacc.vf v10, fa1, v0\n"
    "HDV_HINT 0x0a\n"
    "vfmacc.vf v11, fa1, v1\n"
    "vfmacc.vf v12, fa2, v0\n"
    "vfmacc.vf v13, fa2, v1\n"
    "HDV_HINT 0x00\n"
    "vfmacc.vf v14, fa3, v0\n"
    "vfmacc.vf v15, fa3, v1\n"
    "nop\n"
    // advance pointers.
    "HDV_HINT 0x0a\n"
    "addi t3, t3, 4\n"
    "addi t4, t4, 4\n"
    "addi t5, t5, 4\n"
    "HDV_HINT 0x0a\n"
    "addi t6, t6, 4\n"
    "addi a3, a3, 256\n"
    "addi a4, a4, -32\n"
    // inner back-edge.
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez a4, k_loop_64\n"
    "nop\n"
    "nop\n"

    // store row i.
    "HDV_HINT 0x0a\n"
    "vse32.v v8, (t2)\n"
    "addi a5, t2, 128\n"
    "vse32.v v9, (a5)\n"
    "nop\n"
    // store row i+1.
    "HDV_HINT 0x0a\n"
    "addi a5, t2, 256\n"
    "vse32.v v10, (a5)\n"
    "addi a5, a5, 128\n"
    "vse32.v v11, (a5)\n"
    "nop\n"
    // store row i+2.
    "HDV_HINT 0x0a\n"
    "addi a5, t2, 512\n"
    "vse32.v v12, (a5)\n"
    "addi a5, a5, 128\n"
    "vse32.v v13, (a5)\n"
    "nop\n"
    // store row i+3.
    "HDV_HINT 0x0a\n"
    "addi a5, t2, 768\n"
    "vse32.v v14, (a5)\n"
    "addi a5, a5, 128\n"
    "vse32.v v15, (a5)\n"
    "nop\n"
    // advance to next 4-row block.
    "HDV_HINT 0x0a\n"
    "addi t1, t1, 1024\n"
    "addi t2, t2, 1024\n"
    "addi t0, t0, -1\n"
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez t0, row_block_loop_64\n"
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

// C = A * B, 128x128x128 row-major FP32, 4-row register blocking.
void gemm_f32_128x128x128_4row(const float *A, const float *B, float *C);

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void gemm_f32_128x128x128_4row(const float *A, const float *B, float *C) {
    // ABI: a0=A, a1=B, a2=C.
    //
    // M=N=K=128, 4-row blocking, VL=32 -> 4 vector chunks per row.
    // Accumulators: v8..v11 (row i), v12..v15 (i+1), v16..v19 (i+2), v20..v23 (i+3).
    // Each B[k][:] row = 128 elements = 512B, loaded as 4 chunks.
    // prefetch_mode=3 (4X): N=4 chunks, stride = 512B.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=3\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17))\n"
    ".endm\n"
    ".balign 16\n"
    "vsgemm_128x128_hdv_task_start:\n"

    // setup.
    "HDV_HINT 0x00\n"
    "li a3, 32\n"
    "vsetvli zero, a3, e32, m1, ta, ma\n"
    "li t0, 32\n"
    "HDV_HINT 0x02\n"
    "mv t1, a0\n"
    "mv t2, a2\n"
    "nop\n"

    // outer loop: zero 16 accumulators.
    "row_block_loop_128:\n"
    "HDV_HINT 0x0a, 0, 0, 1, 0\n"
    "vmv.v.i v8, 0\n"
    "vmv.v.i v9, 0\n"
    "vmv.v.i v10, 0\n"
    "HDV_HINT 0x0a\n"
    "vmv.v.i v11, 0\n"
    "vmv.v.i v12, 0\n"
    "vmv.v.i v13, 0\n"
    "HDV_HINT 0x0a\n"
    "vmv.v.i v14, 0\n"
    "vmv.v.i v15, 0\n"
    "vmv.v.i v16, 0\n"
    "HDV_HINT 0x0a\n"
    "vmv.v.i v17, 0\n"
    "vmv.v.i v18, 0\n"
    "vmv.v.i v19, 0\n"
    "HDV_HINT 0x0a\n"
    "vmv.v.i v20, 0\n"
    "vmv.v.i v21, 0\n"
    "vmv.v.i v22, 0\n"
    "HDV_HINT 0x00\n"
    "vmv.v.i v23, 0\n"
    "nop\n"
    "nop\n"
    // 4 A row pointers.
    "HDV_HINT 0x0a\n"
    "mv t3, t1\n"
    "addi t4, t1, 512\n"
    "addi t5, t1, 1024\n"
    "HDV_HINT 0x0a\n"
    "addi t6, t1, 1536\n"
    "mv a3, a1\n"
    "li a4, 4096\n"

    // inner loop.
    "k_loop_128:\n"
    "HDV_HINT 0x00, 0, 0, 1, 0\n"
    "vsetvli zero, a4, e32, m1, ta, ma\n"
    "nop\n"
    "nop\n"
    // 4 scalar loads.
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
    // load B[k][:] - 4 chunks.
    "HDV_HINT 0x0a\n"
    "vle32.v v0, (a3)\n"
    "addi a5, a3, 128\n"
    "vle32.v v1, (a5)\n"
    "HDV_HINT 0x0a\n"
    "addi a5, a3, 256\n"
    "vle32.v v2, (a5)\n"
    "addi a5, a3, 384\n"
    "vle32.v v3, (a5)\n"
    "nop\n"
    // 16 fmacc (4 rows x 4 chunks).
    "HDV_HINT 0x0a\n"
    "vfmacc.vf v8,  fa0, v0\n"
    "vfmacc.vf v9,  fa0, v1\n"
    "vfmacc.vf v10, fa0, v2\n"
    "HDV_HINT 0x0a\n"
    "vfmacc.vf v11, fa0, v3\n"
    "vfmacc.vf v12, fa1, v0\n"
    "vfmacc.vf v13, fa1, v1\n"
    "HDV_HINT 0x0a\n"
    "vfmacc.vf v14, fa1, v2\n"
    "vfmacc.vf v15, fa1, v3\n"
    "vfmacc.vf v16, fa2, v0\n"
    "HDV_HINT 0x0a\n"
    "vfmacc.vf v17, fa2, v1\n"
    "vfmacc.vf v18, fa2, v2\n"
    "vfmacc.vf v19, fa2, v3\n"
    "HDV_HINT 0x00\n"
    "vfmacc.vf v20, fa3, v0\n"
    "vfmacc.vf v21, fa3, v1\n"
    "vfmacc.vf v22, fa3, v2\n"
    "vfmacc.vf v23, fa3, v3\n"
    "nop\n"
    // advance pointers.
    "HDV_HINT 0x0a\n"
    "addi t3, t3, 4\n"
    "addi t4, t4, 4\n"
    "addi t5, t5, 4\n"
    "HDV_HINT 0x0a\n"
    "addi t6, t6, 4\n"
    "addi a3, a3, 512\n"
    "addi a4, a4, -32\n"
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez a4, k_loop_128\n"
    "nop\n"
    "nop\n"

    // store row i (4 chunks).
    "HDV_HINT 0x0a\n"
    "vse32.v v8, (t2)\n"
    "addi a5, t2, 128\n"
    "vse32.v v9, (a5)\n"
    "HDV_HINT 0x0a\n"
    "addi a5, t2, 256\n"
    "vse32.v v10, (a5)\n"
    "addi a5, t2, 384\n"
    "vse32.v v11, (a5)\n"
    "nop\n"
    // store row i+1.
    "HDV_HINT 0x0a\n"
    "addi a5, t2, 512\n"
    "vse32.v v12, (a5)\n"
    "addi a5, a5, 128\n"
    "vse32.v v13, (a5)\n"
    "HDV_HINT 0x0a\n"
    "addi a5, a5, 128\n"
    "vse32.v v14, (a5)\n"
    "addi a5, a5, 128\n"
    "vse32.v v15, (a5)\n"
    "nop\n"
    // store row i+2.
    "HDV_HINT 0x0a\n"
    "addi a5, t2, 1024\n"
    "vse32.v v16, (a5)\n"
    "addi a5, a5, 128\n"
    "vse32.v v17, (a5)\n"
    "HDV_HINT 0x0a\n"
    "addi a5, a5, 128\n"
    "vse32.v v18, (a5)\n"
    "addi a5, a5, 128\n"
    "vse32.v v19, (a5)\n"
    "nop\n"
    // store row i+3.
    "HDV_HINT 0x0a\n"
    "addi a5, t2, 1536\n"
    "vse32.v v20, (a5)\n"
    "addi a5, a5, 128\n"
    "vse32.v v21, (a5)\n"
    "HDV_HINT 0x0a\n"
    "addi a5, a5, 128\n"
    "vse32.v v22, (a5)\n"
    "addi a5, a5, 128\n"
    "vse32.v v23, (a5)\n"
    "nop\n"
    // advance to next 4-row block.
    "HDV_HINT 0x0a\n"
    "addi t1, t1, 1024\n"
    "addi t1, t1, 1024\n"
    "addi t2, t2, 1024\n"
    "HDV_HINT 0x0a\n"
    "addi t2, t2, 1024\n"
    "addi t0, t0, -1\n"
    "nop\n"
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez t0, row_block_loop_128\n"
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
