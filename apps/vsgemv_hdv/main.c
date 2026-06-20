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

#ifndef VSGEMV_HDV_TASK_ENTRY
#define VSGEMV_HDV_TASK_ENTRY 0x80001000UL
#endif

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// dest[i] = dot(matrix[i,:], vector), M=32, N=128, FP32 (true gemv: the input
// vector is loaded, unlike the original benchmark which synthesised x via vid).
void gemv_f32_32x128(const float *matrix, const float *vector, float *dest);
void gemv_f32_32x64(const float *matrix, const float *vector, float *dest);
void gemv_f32_32x256(const float *matrix, const float *vector, float *dest);

int main() {
    gemv_f32_32x128(src1, src2, src1);
    return 0;
}

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void gemv_f32_32x128(const float *matrix, const float *vector, float *dest) {
    // ABI: a0=matrix, a1=vector (x), a2=dest.  Each "addi t2,base,off ; vle v,(t2)"
    // is split so the vle snapshots the freshly bumped base (scalar->vector
    // operand hazard).
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=1\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17))\n"
    ".endm\n"
    ".balign 16\n"
    "vsgemv_hdv_task_start:\n"

    // setup: load the real input vector x (a1), 128 elements = 4 chunks of 32,
    // into v0..v3.  (Deviates from the original benchmark, which synthesised x
    // with vid and ignored the vector argument; this makes it a true gemv.)
    "HDV_HINT 0x00\n"
    "li t3, 32\n"
    "nop\n"
    "nop\n"
    // VL config || load x chunk 0 (reads a1).
    "HDV_HINT 0x02\n"
    "vsetvli zero, t3, e32, m1, ta, ma\n"
    "vle32.v v0, (a1)\n"
    "nop\n"
    // x chunk 1.
    "HDV_HINT 0x00\n"
    "addi t2, a1, 128\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vle32.v v1, (t2)\n"
    "nop\n"
    "nop\n"
    // x chunk 2.
    "HDV_HINT 0x00\n"
    "addi t2, a1, 256\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vle32.v v2, (t2)\n"
    "nop\n"
    "nop\n"
    // x chunk 3.
    "HDV_HINT 0x00\n"
    "addi t2, a1, 384\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vle32.v v3, (t2)\n"
    "nop\n"
    "nop\n"
    // matrix row pointer + row counter.
    "HDV_HINT 0x02\n"
    "mv t0, a0\n"
    "li t6, 1024\n"
    "nop\n"

    // row loop top: VL config || load chunk0 (reads t0).
    "row_loop:\n"
    "HDV_HINT 0x02, 0, 0, 1, 0\n"
    "vsetvli t5, t6, e32, m1, ta, ma\n"
    "vle32.v v4, (t0)\n"
    "nop\n"
    // chunk1 base then load.
    "HDV_HINT 0x00\n"
    "addi t2, t0, 128\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vle32.v v5, (t2)\n"
    "nop\n"
    "nop\n"
    // chunk2 base then load.
    "HDV_HINT 0x00\n"
    "addi t2, t0, 256\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vle32.v v6, (t2)\n"
    "nop\n"
    "nop\n"
    // chunk3 base then load.
    "HDV_HINT 0x00\n"
    "addi t2, t0, 384\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vle32.v v7, (t2)\n"
    "nop\n"
    "nop\n"
    // accumulate (vector chain).
    "HDV_HINT 0x0a\n"
    "vmv.v.i v8, 0\n"
    "vfmacc.vv v8, v4, v0\n"
    "vfmacc.vv v8, v5, v1\n"
    "HDV_HINT 0x02\n"
    "vfmacc.vv v8, v6, v2\n"
    "vfmacc.vv v8, v7, v3\n"
    "nop\n"
    // reduce.
    "HDV_HINT 0x02\n"
    "vmv.v.i v16, 0\n"
    "vfredsum.vs v16, v8, v16\n"
    "nop\n"
    // reduction -> fa0 (vector->scalar writeback), isolate, then store.
    "HDV_HINT 0x00\n"
    "vfmv.f.s fa0, v16\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "fsw fa0, (a2)\n"
    "nop\n"
    "nop\n"
    // pointer bumps + row decrement.
    "HDV_HINT 0x0a\n"
    "addi t0, t0, 512\n"
    "addi a2, a2, 4\n"
    "sub t6, t6, t5\n"
    // branch (loop_end).
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

// dest[i] = dot(matrix[i,:], vector), M=32, N=64, FP32, 2 chunks/row.
void gemv_f32_32x64(const float *matrix, const float *vector, float *dest);

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void gemv_f32_32x64(const float *matrix, const float *vector, float *dest) {
    // ABI: a0=matrix, a1=vector, a2=dest.  N=64 -> 2 chunks, stride=256B.
    // prefetch_mode=2: N=2 chunks.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=2\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17))\n"
    ".endm\n"
    ".balign 16\n"
    "vsgemv_32x64_hdv_task_start:\n"

    // load input vector x (a1): 64 elements = 2 chunks.
    "HDV_HINT 0x00\n"
    "li t3, 32\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x02\n"
    "vsetvli zero, t3, e32, m1, ta, ma\n"
    "vle32.v v0, (a1)\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "addi t2, a1, 128\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vle32.v v1, (t2)\n"
    "nop\n"
    "nop\n"
    // matrix row pointer + row counter.
    "HDV_HINT 0x02\n"
    "mv t0, a0\n"
    "li t6, 1024\n"
    "nop\n"

    // row loop.
    "row_loop_32x64:\n"
    "HDV_HINT 0x02, 0, 0, 1, 0\n"
    "vsetvli t5, t6, e32, m1, ta, ma\n"
    "vle32.v v4, (t0)\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "addi t2, t0, 128\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vle32.v v5, (t2)\n"
    "nop\n"
    "nop\n"
    // accumulate.
    "HDV_HINT 0x0a\n"
    "vmv.v.i v8, 0\n"
    "vfmacc.vv v8, v4, v0\n"
    "vfmacc.vv v8, v5, v1\n"
    "nop\n"
    // reduce.
    "HDV_HINT 0x02\n"
    "vmv.v.i v16, 0\n"
    "vfredsum.vs v16, v8, v16\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vfmv.f.s fa0, v16\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "fsw fa0, (a2)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x0a\n"
    "addi t0, t0, 256\n"
    "addi a2, a2, 4\n"
    "sub t6, t6, t5\n"
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez t6, row_loop_32x64\n"
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

// dest[i] = dot(matrix[i,:], vector), M=32, N=256, FP32, 8 chunks/row.
// HDV prefetch_mode max is 3 (4X); ideal would be 8X.
void gemv_f32_32x256(const float *matrix, const float *vector, float *dest);

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void gemv_f32_32x256(const float *matrix, const float *vector, float *dest) {
    // ABI: a0=matrix, a1=vector, a2=dest.  N=256 -> 8 chunks, stride=1024B.
    // prefetch_mode=3 (4X, best effort for N=8 since HDV only has 2 bits).
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=3\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17))\n"
    ".endm\n"
    ".balign 16\n"
    "vsgemv_32x256_hdv_task_start:\n"

    // load input vector x: 256 elements = 8 chunks into v0..v7.
    "HDV_HINT 0x00\n"
    "li t3, 32\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x02\n"
    "vsetvli zero, t3, e32, m1, ta, ma\n"
    "vle32.v v0, (a1)\n"
    "nop\n"
    // chunks 1-3.
    "HDV_HINT 0x0a\n"
    "addi t2, a1, 128\n"
    "vle32.v v1, (t2)\n"
    "addi t2, a1, 256\n"
    "HDV_HINT 0x00\n"
    "vle32.v v2, (t2)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "addi t2, a1, 384\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vle32.v v3, (t2)\n"
    "nop\n"
    "nop\n"
    // chunks 4-7.
    "HDV_HINT 0x00\n"
    "addi t2, a1, 512\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vle32.v v4, (t2)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x0a\n"
    "addi t2, a1, 640\n"
    "vle32.v v5, (t2)\n"
    "addi t2, a1, 768\n"
    "HDV_HINT 0x00\n"
    "vle32.v v6, (t2)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "addi t2, a1, 896\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vle32.v v7, (t2)\n"
    "nop\n"
    "nop\n"
    // matrix row pointer + row counter.
    "HDV_HINT 0x02\n"
    "mv t0, a0\n"
    "li t6, 1024\n"
    "nop\n"

    // row loop.
    "row_loop_32x256:\n"
    "HDV_HINT 0x02, 0, 0, 1, 0\n"
    "vsetvli t5, t6, e32, m1, ta, ma\n"
    "vle32.v v16, (t0)\n"
    "nop\n"
    // chunks 1-3.
    "HDV_HINT 0x0a\n"
    "addi t2, t0, 128\n"
    "vle32.v v17, (t2)\n"
    "addi t2, t0, 256\n"
    "HDV_HINT 0x00\n"
    "vle32.v v18, (t2)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "addi t2, t0, 384\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vle32.v v19, (t2)\n"
    "nop\n"
    "nop\n"
    // chunks 4-7.
    "HDV_HINT 0x00\n"
    "addi t2, t0, 512\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vle32.v v20, (t2)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x0a\n"
    "addi t2, t0, 640\n"
    "vle32.v v21, (t2)\n"
    "addi t2, t0, 768\n"
    "HDV_HINT 0x00\n"
    "vle32.v v22, (t2)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "addi t2, t0, 896\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vle32.v v23, (t2)\n"
    "nop\n"
    "nop\n"
    // accumulate.
    "HDV_HINT 0x0a\n"
    "vmv.v.i v24, 0\n"
    "vfmacc.vv v24, v16, v0\n"
    "vfmacc.vv v24, v17, v1\n"
    "HDV_HINT 0x0a\n"
    "vfmacc.vv v24, v18, v2\n"
    "vfmacc.vv v24, v19, v3\n"
    "vfmacc.vv v24, v20, v4\n"
    "HDV_HINT 0x0a\n"
    "vfmacc.vv v24, v21, v5\n"
    "vfmacc.vv v24, v22, v6\n"
    "vfmacc.vv v24, v23, v7\n"
    "nop\n"
    // reduce.
    "HDV_HINT 0x02\n"
    "vmv.v.i v8, 0\n"
    "vfredsum.vs v8, v24, v8\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "vfmv.f.s fa0, v8\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "fsw fa0, (a2)\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x0a\n"
    "addi t0, t0, 1024\n"
    "addi a2, a2, 4\n"
    "sub t6, t6, t5\n"
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez t6, row_loop_32x256\n"
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
