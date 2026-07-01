// ============================================================================
// vsgemm_asm — tightly-coupled (standard Ara) counterpart of vsgemm_hdv.
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

#define TOTAL_ELEMENTS 32768

#ifndef VSGEMM_HDV_TASK_ENTRY
#define VSGEMM_HDV_TASK_ENTRY 0x80001000UL
#endif

// Uniform AVL knob (build injects -DASM_AVL=<n> via `make ... asm_avl=<n>`).
// Default = the value historically hard-coded in the m4 runtime-N kernel call
// (32), so a plain `make` is byte-identical to before.  Only the m4
// (GEMM_LMUL==4) runtime-dimension call uses it; the m1 fixed-32 path is left
// untouched, and TOTAL_ELEMENTS still sizes the extern data arrays.
#ifndef ASM_AVL
#define ASM_AVL 32
#endif

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// ── GEMM variant selector: GEMM_LMUL x GEMM_ROWS ────────────────────────────
// GEMM_LMUL = 1 : the ORIGINAL m1 kernels, fixed 32x32x32, VLMAX=32 (one vector
//                 register = one 32-wide row), dense packet256+cross packing.
//                 These are the validated runs (4row=10847, 2row=19248,
//                 1row=31846 cyc; L2 256/256 bit-exact for 4row).
// GEMM_LMUL = 4 : the unified m4 kernels, RUNTIME dimension N<=128 (a3, injected
//                 via +HDV_A3=N), VLMAX=128 (one group = a full N-wide row), VL
//                 set once in setup, strides via slli.  Sweepable across N.
// GEMM_ROWS = 1 | 2 | 4 : register-blocking rows = # scalar A load streams packed
//                 into one EP per k-iteration (the pipelined-LSU study variable).
// avl_sweep / the Makefile pass -DGEMM_LMUL and -DGEMM_ROWS.  Both kept, both
// selectable; only ONE function compiles into .hdv_task (it becomes the entry).
#ifndef GEMM_LMUL
#define GEMM_LMUL 1
#endif
#ifndef GEMM_ROWS
#define GEMM_ROWS 4
#endif

// m1 fixed-32 variants.
void gemm_f32_32x32x32_1row(const float *A, const float *B, float *C);
void gemm_f32_32x32x32_2row(const float *A, const float *B, float *C);
void gemm_f32_32x32x32_4row(const float *A, const float *B, float *C);
// m4 runtime-N variants.
void gemm_f32_1row(const float *A, const float *B, float *C, int n);
void gemm_f32_2row(const float *A, const float *B, float *C, int n);
void gemm_f32_4row(const float *A, const float *B, float *C, int n);

int main() {
    HW_CNT_READY;
#ifndef SPIKE
    perf_time();
#endif
#if GEMM_LMUL == 1
#if GEMM_ROWS == 1
    gemm_f32_32x32x32_1row(src1, src2, src1);
#elif GEMM_ROWS == 2
    gemm_f32_32x32x32_2row(src1, src2, src1);
#else
    gemm_f32_32x32x32_4row(src1, src2, src1);
#endif
#else
#if GEMM_ROWS == 1
    gemm_f32_1row(src1, src2, src1, ASM_AVL);
#elif GEMM_ROWS == 2
    gemm_f32_2row(src1, src2, src1, ASM_AVL);
#else
    gemm_f32_4row(src1, src2, src1, ASM_AVL);
#endif
#endif
#ifndef SPIKE
    perf_time();
#endif
    HW_CNT_NOT_READY;
    return 0;
}

#if GEMM_LMUL == 1
// ════════════════════════ m1 fixed-32 kernels ═══════════════════════════════
#if GEMM_ROWS == 1
__attribute__((naked, 
               target("arch=rv64gcv_zfh_zvfh")))
void gemm_f32_32x32x32_1row(const float *A, const float *B, float *C) {
    // ABI: a0=A, a1=B, a2=C.  m1, fixed 32, 1 scalar A load stream per k.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".balign 16\n"
    "vsgemm_hdv_task_start:\n"
    "li a3, 1024\n"
    "vsetvli zero, a3, e32, m1, ta, ma\n"
    "li t0, 32\n"
    "mv t1, a0\n"
    "mv t2, a2\n"
    "nop\n"
    "row_block_loop_32_1r:\n"
    "vmv.v.i v8, 0\n"
    "nop\n"
    "nop\n"
    "mv t3, t1\n"
    "mv a3, a1\n"
    "li a4, 1024\n"
    "k_loop_32_1r:\n"
    "flw fa0, 0(t3)\n"
    "nop\n"
    "nop\n"
    "vle32.v v0, (a3)\n"
    "vfmacc.vf v8, fa0, v0\n"
    "nop\n"
    "addi t3, t3, 4\n"
    "addi a3, a3, 128\n"
    "addi a4, a4, -32\n"
    "bnez a4, k_loop_32_1r\n"
    "nop\n"
    "nop\n"
    "vse32.v v8, (t2)\n"
    "nop\n"
    "nop\n"
    "addi t1, t1, 128\n"
    "addi t2, t2, 128\n"
    "addi t0, t0, -1\n"
    "bnez t0, row_block_loop_32_1r\n"
    "nop\n"
    "nop\n"
    "ret\n"
    "nop\n"
    "nop\n"
    ".option pop\n"
    );
}
#elif GEMM_ROWS == 2
__attribute__((naked, 
               target("arch=rv64gcv_zfh_zvfh")))
void gemm_f32_32x32x32_2row(const float *A, const float *B, float *C) {
    // ABI: a0=A, a1=B, a2=C.  m1, fixed 32, 2 A load streams packed per k.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".balign 16\n"
    "vsgemm_hdv_task_start:\n"
    "li a3, 1024\n"
    "vsetvli zero, a3, e32, m1, ta, ma\n"
    "li t0, 16\n"
    "mv t1, a0\n"
    "mv t2, a2\n"
    "nop\n"
    "row_block_loop_32_2r:\n"
    "vmv.v.i v8, 0\n"
    "vmv.v.i v9, 0\n"
    "nop\n"
    "mv t3, t1\n"
    "mv a3, a1\n"
    "li a4, 1024\n"
    "k_loop_32_2r:\n"
    "flw fa0, 0(t3)\n"
    "flw fa1, 128(t3)\n"
    "nop\n"
    "vle32.v v0, (a3)\n"
    "vfmacc.vf v8, fa0, v0\n"
    "nop\n"
    "vfmacc.vf v9, fa1, v0\n"
    "nop\n"
    "nop\n"
    "addi t3, t3, 4\n"
    "addi a3, a3, 128\n"
    "addi a4, a4, -32\n"
    "bnez a4, k_loop_32_2r\n"
    "nop\n"
    "nop\n"
    "vse32.v v8, (t2)\n"
    "nop\n"
    "nop\n"
    "addi a5, t2, 128\n"
    "nop\n"
    "nop\n"
    "vse32.v v9, (a5)\n"
    "nop\n"
    "nop\n"
    "addi t1, t1, 256\n"
    "addi t2, t2, 256\n"
    "addi t0, t0, -1\n"
    "bnez t0, row_block_loop_32_2r\n"
    "nop\n"
    "nop\n"
    "ret\n"
    "nop\n"
    "nop\n"
    ".option pop\n"
    );
}
#else
#include "vsgemm_m1_4row.inc"
#endif
#else
// ════════════════════════ m4 runtime-N kernels ══════════════════════════════

#if GEMM_ROWS == 1
__attribute__((naked, 
               target("arch=rv64gcv_zfh_zvfh")))
void gemm_f32_1row(const float *A, const float *B, float *C, int n) {
    // ABI: a0=A, a1=B, a2=C, a3=N.  1-row = ONE scalar A load stream per k
    // (baseline: nothing for the pipelined LSU to overlap).
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".balign 16\n"
    "vsgemm_hdv_task_start:\n"
    "addi sp, sp, -32\n"
    "sd s0, 0(sp)\n"
    "sd s1, 8(sp)\n"
    "sd s2, 16(sp)\n"

    // setup: N -> s0, VL=N (m4, once), stride s1 = N*4, counters + bases.
    "mv s0, a3\n"
    "vsetvli zero, s0, e32, m4, ta, ma\n"
    "slli s1, a3, 2\n"
    "mv t0, s0\n"
    "mv t1, a0\n"
    "mv t2, a2\n"

    ".balign 16\n"
    "row_block_loop:\n"
    "vmv.v.i v4, 0\n"
    "nop\n"
    "nop\n"
    "mv t3, t1\n"
    "mv a4, a1\n"
    "mv a5, s0\n"

    ".balign 16\n"
    "k_loop:\n"
    // 1 scalar A load (own EP), then B row + 1 vfmacc.
    "flw fa0, 0(t3)\n"
    "nop\n"
    "nop\n"
    "vle32.v v0, (a4)\n"
    "vfmacc.vf v4, fa0, v0\n"
    "nop\n"
    "addi t3, t3, 4\n"
    "add a4, a4, s1\n"
    "addi a5, a5, -1\n"
    "bnez a5, k_loop\n"
    "nop\n"
    "nop\n"

    "vse32.v v4, (t2)\n"
    "nop\n"
    "nop\n"
    "add t1, t1, s1\n"
    "add t2, t2, s1\n"
    "addi t0, t0, -1\n"
    "bnez t0, row_block_loop\n"
    "nop\n"
    "nop\n"

    "ld s0, 0(sp)\n"
    "ld s1, 8(sp)\n"
    "ld s2, 16(sp)\n"
    "addi sp, sp, 32\n"
    "ret\n"
    "nop\n"
    "nop\n"
    ".option pop\n"
    );
}
#elif GEMM_ROWS == 2
__attribute__((naked, 
               target("arch=rv64gcv_zfh_zvfh")))
void gemm_f32_2row(const float *A, const float *B, float *C, int n) {
    // ABI: a0=A, a1=B, a2=C, a3=N.  2-row = TWO A load streams packed per k.
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".balign 16\n"
    "vsgemm_hdv_task_start:\n"
    "addi sp, sp, -32\n"
    "sd s0, 0(sp)\n"
    "sd s1, 8(sp)\n"
    "sd s2, 16(sp)\n"

    // setup: N -> s0, VL=N (m4, once), s1 = N*4, s2 = 2*N*4 (block stride).
    "mv s0, a3\n"
    "vsetvli zero, s0, e32, m4, ta, ma\n"
    "slli s1, a3, 2\n"
    "slli s2, a3, 3\n"
    "srli t0, a3, 1\n"
    "mv t1, a0\n"
    "mv t2, a2\n"
    "nop\n"

    ".balign 16\n"
    "row_block_loop:\n"
    "vmv.v.i v4, 0\n"
    "vmv.v.i v8, 0\n"
    "nop\n"
    // A row pointers (rows i, i+1) + B base + k count.
    "mv t3, t1\n"
    "add t4, t1, s1\n"
    "mv a4, a1\n"
    "mv a5, s0\n"
    "nop\n"
    "nop\n"

    ".balign 16\n"
    "k_loop:\n"
    // 2 A loads packed into ONE EP.
    "flw fa0, 0(t3)\n"
    "flw fa1, 0(t4)\n"
    "nop\n"
    // B row + first vfmacc.
    "vle32.v v0, (a4)\n"
    "vfmacc.vf v4, fa0, v0\n"
    "nop\n"
    // second vfmacc.
    "vfmacc.vf v8, fa1, v0\n"
    "nop\n"
    "nop\n"
    // pointer bumps + k decrement.
    "addi t3, t3, 4\n"
    "addi t4, t4, 4\n"
    "add a4, a4, s1\n"
    "addi a5, a5, -1\n"
    "bnez a5, k_loop\n"
    "nop\n"

    // store rows i, i+1.
    "vse32.v v4, (t2)\n"
    "nop\n"
    "nop\n"
    "add a6, t2, s1\n"
    "nop\n"
    "nop\n"
    "vse32.v v8, (a6)\n"
    "nop\n"
    "nop\n"
    // advance to next 2-row block.
    "add t1, t1, s2\n"
    "add t2, t2, s2\n"
    "addi t0, t0, -1\n"
    "bnez t0, row_block_loop\n"
    "nop\n"
    "nop\n"

    "ld s0, 0(sp)\n"
    "ld s1, 8(sp)\n"
    "ld s2, 16(sp)\n"
    "addi sp, sp, 32\n"
    "ret\n"
    "nop\n"
    "nop\n"
    ".option pop\n"
    );
}
#else
__attribute__((naked, 
               target("arch=rv64gcv_zfh_zvfh")))
void gemm_f32_4row(const float *A, const float *B, float *C, int n) {
    // ABI: a0=A, a1=B, a2=C, a3=N.  4-row = FOUR A load streams packed per k
    // (the case the pipelined LSU overlaps maximally).
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".balign 16\n"
    "vsgemm_hdv_task_start:\n"
    "addi sp, sp, -32\n"
    "sd s0, 0(sp)\n"
    "sd s1, 8(sp)\n"
    "sd s2, 16(sp)\n"

    // setup: N -> s0, VL=N (m4, once), s1 = N*4, s2 = 4*N*4 (block stride).
    "mv s0, a3\n"
    "vsetvli zero, s0, e32, m4, ta, ma\n"
    "slli s1, a3, 2\n"
    "slli s2, a3, 4\n"
    "srli t0, a3, 2\n"
    "mv t1, a0\n"
    "mv t2, a2\n"
    "nop\n"

    ".balign 16\n"
    "row_block_loop:\n"
    "vmv.v.i v4, 0\n"
    "vmv.v.i v8, 0\n"
    "vmv.v.i v12, 0\n"
    "vmv.v.i v16, 0\n"
    "nop\n"
    "nop\n"
    // A row pointers (rows i..i+3) — chained adds of the runtime stride s1.
    "mv t3, t1\n"
    "add t4, t1, s1\n"
    "add t5, t4, s1\n"
    "add t6, t5, s1\n"
    "mv a4, a1\n"
    "mv a5, s0\n"

    ".balign 16\n"
    "k_loop:\n"
    // 4 A loads packed into ONE EP (p-bits 0x2a keep slots 1/3/5).
    "flw fa0, 0(t3)\n"
    "flw fa1, 0(t4)\n"
    "flw fa2, 0(t5)\n"
    "flw fa3, 0(t6)\n"
    "vle32.v v0, (a4)\n"
    "nop\n"
    "nop\n"
    // 4 vfmacc (one EP — Ara resolves the vector deps; all read v0).
    "vfmacc.vf v4,  fa0, v0\n"
    "vfmacc.vf v8,  fa1, v0\n"
    "vfmacc.vf v12, fa2, v0\n"
    "vfmacc.vf v16, fa3, v0\n"
    "nop\n"
    "nop\n"
    "nop\n"
    // A pointer bumps.
    "addi t3, t3, 4\n"
    "addi t4, t4, 4\n"
    "addi t5, t5, 4\n"
    // last A bump + B bump + k decrement.
    "addi t6, t6, 4\n"
    "add a4, a4, s1\n"
    "addi a5, a5, -1\n"
    "bnez a5, k_loop\n"
    "nop\n"
    "nop\n"

    // store rows i..i+3 (bases t2, t2+s1, t2+2s1, t2+3s1).
    "vse32.v v4, (t2)\n"
    "nop\n"
    "nop\n"
    "add a6, t2, s1\n"
    "nop\n"
    "nop\n"
    "vse32.v v8, (a6)\n"
    "nop\n"
    "nop\n"
    "add a6, a6, s1\n"
    "nop\n"
    "nop\n"
    "vse32.v v12, (a6)\n"
    "nop\n"
    "nop\n"
    "add a6, a6, s1\n"
    "nop\n"
    "nop\n"
    "vse32.v v16, (a6)\n"
    "nop\n"
    "nop\n"
    // advance to next 4-row block.
    "add t1, t1, s2\n"
    "add t2, t2, s2\n"
    "addi t0, t0, -1\n"
    "bnez t0, row_block_loop\n"
    "nop\n"
    "nop\n"

    "ld s0, 0(sp)\n"
    "ld s1, 8(sp)\n"
    "ld s2, 16(sp)\n"
    "addi sp, sp, 32\n"
    "ret\n"
    "nop\n"
    "nop\n"
    ".option pop\n"
    );
}
#endif
#endif
