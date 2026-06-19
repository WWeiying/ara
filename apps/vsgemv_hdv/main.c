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

// dest[i] = dot(matrix[i,:], x), M=32, N=128, FP32 (x built from vid).
void gemv_f32_32x128(const float *matrix, const float *vector, float *dest);

int main() {
    gemv_f32_32x128(src1, src2, src1);
    return 0;
}

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void gemv_f32_32x128(const float *matrix, const float *vector, float *dest) {
    // ABI: a0=matrix, a2=dest.  Each "addi t2,t0,off ; vle v,(t2)" is split so
    // the vle snapshots the freshly bumped base (scalar->vector operand hazard).
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16))\n"
    ".endm\n"
    ".balign 16\n"
    "vsgemv_hdv_task_start:\n"

    // setup: build x = {0,1,2,...} replicated in v0..v3.
    "HDV_HINT 0x00\n"
    "li t3, 32\n"
    "vsetvli zero, t3, e32, m1, ta, ma\n"
    "vid.v v0\n"
    "HDV_HINT 0x0a\n"
    "vfcvt.f.x.v v0, v0\n"
    "vmv.v.v v1, v0\n"
    "vmv.v.v v2, v0\n"
    "HDV_HINT 0x02\n"
    "vmv.v.v v3, v0\n"
    "mv t0, a0\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "li t6, 1024\n"
    "nop\n"
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
