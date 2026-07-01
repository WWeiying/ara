// ============================================================================
// vsspmv_asm — tightly-coupled (standard Ara) counterpart of vsspmv_hdv.
// Auto-derived from the HDV version: HDV packetization stripped (HDV_HINT
// lui-x0 packet headers removed; .hdv_task section -> .text naked function).
// Identical vector instruction stream; the scalar core issues vector ops
// directly to Ara (no decoupled front-end / no software prefetch hints).
// For main-branch tightly-coupled architecture testing.  NOT yet tested.
// ============================================================================
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
#define SPMV_ROWS 32
#define SPMV_NNZ  32

#ifndef VSSPMV_HDV_TASK_ENTRY
#define VSSPMV_HDV_TASK_ENTRY 0x80001000UL
#endif

// Uniform ASM_AVL knob (build injects -DASM_AVL=<n> via `make ... asm_avl=<n>`).
// Default = the value used today so a plain make is byte-identical.
#ifndef ASM_AVL
#define ASM_AVL TOTAL_ELEMENTS
#endif

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(128), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(128), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// Under HDV the TB jumps straight to the kernel entry, so main()'s runtime
// init loop never runs.  col_idx must therefore live in loaded .rodata with the
// values baked in at compile time.  Each of the 32 rows is the index run {0..31}.
#define SPMV_ROW_IDX \
  0u,1u,2u,3u,4u,5u,6u,7u,8u,9u,10u,11u,12u,13u,14u,15u, \
  16u,17u,18u,19u,20u,21u,22u,23u,24u,25u,26u,27u,28u,29u,30u,31u
#define SPMV_ROW_IDX_X2  SPMV_ROW_IDX, SPMV_ROW_IDX
#define SPMV_ROW_IDX_X4  SPMV_ROW_IDX_X2, SPMV_ROW_IDX_X2
#define SPMV_ROW_IDX_X8  SPMV_ROW_IDX_X4, SPMV_ROW_IDX_X4
#define SPMV_ROW_IDX_X16 SPMV_ROW_IDX_X8, SPMV_ROW_IDX_X8
#define SPMV_ROW_IDX_X32 SPMV_ROW_IDX_X16, SPMV_ROW_IDX_X16
static const uint32_t col_idx[SPMV_ROWS * SPMV_NNZ]
    __attribute__((aligned(128))) = { SPMV_ROW_IDX_X32 };

void spmv_f32_32x32(const float *val, const uint32_t *col_idx,
                    const float *x, float *y);

int main() {
    HW_CNT_READY;
#ifndef SPIKE
    perf_time();
#endif
    spmv_f32_32x32(src1, col_idx, src2, src2 + 64);
#ifndef SPIKE
    perf_time();
#endif
    HW_CNT_NOT_READY;
    return 0;
}

__attribute__((naked, 
               target("arch=rv64gcv_zfh_zvfh")))
void spmv_f32_32x32(const float *val, const uint32_t *col_idx,
                    const float *x, float *y) {
    // ABI: a0=val, a1=col_idx, a2=x (gather base), a3=y.  32 nnz/row, 32 rows.
    //
    // Vector-vector chains are packed freely (Ara resolves vector deps); the
    // scalar reduction-store tail (vfmv.f.s -> fsw) and the zero-seed scalar are
    // isolated so the vector->scalar writeback and the scalar operand snapshot
    // are observed in order.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".balign 16\n"
    "vsspmv_hdv_task_start:\n"
    "addi sp, sp, -16\n"
    "sd s0, 0(sp)\n"

    // setup: row count, then VL config || row pointers.
    "li t0, 1024\n"
    "mv t1, a0\n"
    "mv t2, a1\n"
    "vsetvli s0, t0, e32, m1, ta, ma\n"
    "mv t3, a3\n"
    "nop\n"

    // Row loop.  The HDV same-EP hazard bypass assumes every instruction packed
    // into one EP is INDEPENDENT (software p-bit guarantee), so a producer and a
    // consumer must never share an EP — otherwise their RAW hazard is bypassed and
    // the consumer reads a stale operand.  The dependent chain here is
    //   vle v1 -> vsll v1 -> vluxei v1 -> vfmul v2
    // so vsll, vluxei and vfmul each get their own EP.  Only the two independent
    // loads (v0, v1) may share an EP.
    "row_loop:\n"
    "vle32.v v0, (t1)\n"
    "vle32.v v1, (t2)\n"
    "nop\n"
    "vsll.vi v1, v1, 2\n"
    "nop\n"
    "nop\n"
    "vluxei32.v v2, (a2), v1\n"
    "nop\n"
    "nop\n"
    "vfmul.vv v3, v0, v2\n"
    "nop\n"
    "nop\n"
    // zero seed scalar (isolate before vfmv.v.f reads it).
    "fmv.w.x ft0, zero\n"
    "nop\n"
    "nop\n"
    // seed vector → isolate (vfmv.v.f writes v16, must commit before reduction).
    "vfmv.v.f v16, ft0\n"
    "nop\n"
    "nop\n"
    // reduce (reads seed v16, writes result v16 — separate EP avoids WAW bypass).
    "vfredusum.vs v16, v3, v16\n"
    "nop\n"
    "nop\n"
    // reduction -> ft1 (vector->scalar writeback), isolate.
    "vfmv.f.s ft1, v16\n"
    "nop\n"
    "nop\n"
    // store y[i] (reads ft1 from writeback).
    "fsw ft1, 0(t3)\n"
    "nop\n"
    "nop\n"
    // pointer bumps + row decrement.
    "addi t1, t1, 128\n"
    "addi t2, t2, 128\n"
    "addi t3, t3, 4\n"
    "addi t0, t0, -32\n"
    "nop\n"
    "nop\n"
    // branch (loop_end).
    "bnez t0, row_loop\n"
    "nop\n"
    "nop\n"

    "ld s0, 0(sp)\n"
    "addi sp, sp, 16\n"
    "ret\n"
    "nop\n"
    "nop\n"
    ".option pop\n"
    );
}
