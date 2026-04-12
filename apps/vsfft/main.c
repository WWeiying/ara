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

#define TOTAL_ELEMENTS 256
#define FFT256_TW_COUNT 255

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(128), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(128), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

extern const float fft256_tw_re[FFT256_TW_COUNT];
extern const float fft256_tw_im[FFT256_TW_COUNT];

extern const uint32_t _fft256_tw_re_size;
extern const uint32_t _fft256_tw_im_size;

void fft_r2dif_f32_256(float *samples_re, float *samples_im);

int main() {

    fft_r2dif_f32_256(src1, src2);

    return 0;
}

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void fft_r2dif_f32_256(float *samples_re, float *samples_im) {
    __asm__ volatile(
#ifndef SPIKE
        "rdcycle zero\n"
#endif
        // ============================================================
        // Stage 0: step=256, half=128
        // avl-driven, vl=32 each time
        // twiddle offset = 0B
        // ============================================================
        "la a2, fft256_tw_re\n"
        "la a3, fft256_tw_im\n"
        "mv t1, a0\n"                  // upper re ptr
        "mv t2, a1\n"                  // upper im ptr
        "addi t3, a0, 512\n"           // lower re ptr
        "addi t4, a1, 512\n"           // lower im ptr
        "li a4, 128\n"                 // avl = half

        "s0_chunk:\n"
        "vsetvli t0, a4, e32, m1, ta, ma\n"
        "vle32.v v0, (t1)\n"           // ur
        "vle32.v v1, (t2)\n"           // ui
        "vle32.v v2, (t3)\n"           // lr
        "vle32.v v3, (t4)\n"           // li
        "vle32.v v8, (a2)\n"           // wr
        "vle32.v v9, (a3)\n"           // wi

        "vfadd.vv v4, v0, v2\n"        // sumr
        "vfadd.vv v5, v1, v3\n"        // sumi
        "vfsub.vv v6, v0, v2\n"        // diffr
        "vfsub.vv v7, v1, v3\n"        // diffi

        "vfmul.vv v10, v6, v8\n"
        "vfnmsac.vv v10, v7, v9\n"     // lowr = diffr*wr - diffi*wi
        "vfmul.vv v11, v6, v9\n"
        "vfmacc.vv v11, v7, v8\n"      // lowi = diffr*wi + diffi*wr

        "vse32.v v4, (t1)\n"
        "vse32.v v5, (t2)\n"
        "vse32.v v10, (t3)\n"
        "vse32.v v11, (t4)\n"

        "slli a5, t0, 2\n"
        "add t1, t1, a5\n"
        "add t2, t2, a5\n"
        "add t3, t3, a5\n"
        "add t4, t4, a5\n"
        "add a2, a2, a5\n"
        "add a3, a3, a5\n"
        "sub a4, a4, t0\n"
        "bnez a4, s0_chunk\n"

        // ============================================================
        // Stage 1: step=128, half=64, groups=2
        // avl-driven, vl=32
        // twiddle offset = 512B
        // ============================================================
        "la t6, fft256_tw_re\n"
        "addi t6, t6, 512\n"
        "la a7, fft256_tw_im\n"
        "addi a7, a7, 512\n"
        "mv t1, a0\n"                  // group base re
        "mv t2, a1\n"                  // group base im
        "li t5, 2\n"                   // group count

        "s1_group:\n"
        "mv a2, t6\n"                  // tw_re base for this group
        "mv a3, a7\n"                  // tw_im base for this group
        "mv t3, t1\n"                  // upper re ptr
        "mv t4, t2\n"                  // upper im ptr
        "addi a4, t1, 256\n"           // lower re ptr
        "addi a5, t2, 256\n"           // lower im ptr
        "li a6, 64\n"                  // avl = half

        "s1_chunk:\n"
        "vsetvli t0, a6, e32, m1, ta, ma\n"
        "vle32.v v0, (t3)\n"
        "vle32.v v1, (t4)\n"
        "vle32.v v2, (a4)\n"
        "vle32.v v3, (a5)\n"
        "vle32.v v8, (a2)\n"
        "vle32.v v9, (a3)\n"

        "vfadd.vv v4, v0, v2\n"
        "vfadd.vv v5, v1, v3\n"
        "vfsub.vv v6, v0, v2\n"
        "vfsub.vv v7, v1, v3\n"

        "vfmul.vv v10, v6, v8\n"
        "vfnmsac.vv v10, v7, v9\n"
        "vfmul.vv v11, v6, v9\n"
        "vfmacc.vv v11, v7, v8\n"

"vse32.v v4, (t3)\n"
"vse32.v v5, (t4)\n"
"vse32.v v10, (a4)\n"
"vse32.v v11, (a5)\n"

"sub a6, a6, t0\n"
"slli t0, t0, 2\n"
"add t3, t3, t0\n"
"add t4, t4, t0\n"
"add a4, a4, t0\n"
"add a5, a5, t0\n"
"add a2, a2, t0\n"
"add a3, a3, t0\n"
"bnez a6, s1_chunk\n"

        "addi t1, t1, 512\n"
        "addi t2, t2, 512\n"
        "addi t5, t5, -1\n"
        "bnez t5, s1_group\n"

        // ============================================================
        // Stage 2: step=64, half=32, groups=4
        // fixed vl=32
        // twiddle loaded once and reused across groups
        // twiddle offset = 768B
        // ============================================================
        "li t0, 32\n"
        "vsetvli zero, t0, e32, m1, ta, ma\n"
        "la t6, fft256_tw_re\n"
        "addi t6, t6, 768\n"
        "la a7, fft256_tw_im\n"
        "addi a7, a7, 768\n"
        "vle32.v v8, (t6)\n"
        "vle32.v v9, (a7)\n"

        "mv t1, a0\n"
        "mv t2, a1\n"
        "li t5, 4\n"

        "s2_group:\n"
        "vle32.v v0, (t1)\n"
        "vle32.v v1, (t2)\n"
        "addi t3, t1, 128\n"
        "addi t4, t2, 128\n"
        "vle32.v v2, (t3)\n"
        "vle32.v v3, (t4)\n"

        "vfadd.vv v4, v0, v2\n"
        "vfadd.vv v5, v1, v3\n"
        "vfsub.vv v6, v0, v2\n"
        "vfsub.vv v7, v1, v3\n"

        "vfmul.vv v10, v6, v8\n"
        "vfnmsac.vv v10, v7, v9\n"
        "vfmul.vv v11, v6, v9\n"
        "vfmacc.vv v11, v7, v8\n"

        "vse32.v v4, (t1)\n"
        "vse32.v v5, (t2)\n"
        "vse32.v v10, (t3)\n"
        "vse32.v v11, (t4)\n"

        "addi t1, t1, 256\n"
        "addi t2, t2, 256\n"
        "addi t5, t5, -1\n"
        "bnez t5, s2_group\n"

        // ============================================================
        // Stage 3: step=32, half=16, groups=8
        // fixed vl=16
        // twiddle loaded once and reused across groups
        // twiddle offset = 896B
        // ============================================================
        "li t0, 16\n"
        "vsetvli zero, t0, e32, m1, ta, ma\n"
        "la t6, fft256_tw_re\n"
        "addi t6, t6, 896\n"
        "la a7, fft256_tw_im\n"
        "addi a7, a7, 896\n"
        "vle32.v v8, (t6)\n"
        "vle32.v v9, (a7)\n"

        "mv t1, a0\n"
        "mv t2, a1\n"
        "li t5, 8\n"

        "s3_group:\n"
        "vle32.v v0, (t1)\n"
        "vle32.v v1, (t2)\n"
        "addi t3, t1, 64\n"
        "addi t4, t2, 64\n"
        "vle32.v v2, (t3)\n"
        "vle32.v v3, (t4)\n"

        "vfadd.vv v4, v0, v2\n"
        "vfadd.vv v5, v1, v3\n"
        "vfsub.vv v6, v0, v2\n"
        "vfsub.vv v7, v1, v3\n"

        "vfmul.vv v10, v6, v8\n"
        "vfnmsac.vv v10, v7, v9\n"
        "vfmul.vv v11, v6, v9\n"
        "vfmacc.vv v11, v7, v8\n"

        "vse32.v v4, (t1)\n"
        "vse32.v v5, (t2)\n"
        "vse32.v v10, (t3)\n"
        "vse32.v v11, (t4)\n"

        "addi t1, t1, 128\n"
        "addi t2, t2, 128\n"
        "addi t5, t5, -1\n"
        "bnez t5, s3_group\n"

        // ============================================================
        // Stage 4: step=16, half=8, groups=16
        // fixed vl=8
        // twiddle loaded once and reused across groups
        // twiddle offset = 960B
        // ============================================================
        "li t0, 8\n"
        "vsetvli zero, t0, e32, m1, ta, ma\n"
        "la t6, fft256_tw_re\n"
        "addi t6, t6, 960\n"
        "la a7, fft256_tw_im\n"
        "addi a7, a7, 960\n"
        "vle32.v v8, (t6)\n"
        "vle32.v v9, (a7)\n"

        "mv t1, a0\n"
        "mv t2, a1\n"
        "li t5, 16\n"

        "s4_group:\n"
        "vle32.v v0, (t1)\n"
        "vle32.v v1, (t2)\n"
        "addi t3, t1, 32\n"
        "addi t4, t2, 32\n"
        "vle32.v v2, (t3)\n"
        "vle32.v v3, (t4)\n"

        "vfadd.vv v4, v0, v2\n"
        "vfadd.vv v5, v1, v3\n"
        "vfsub.vv v6, v0, v2\n"
        "vfsub.vv v7, v1, v3\n"

        "vfmul.vv v10, v6, v8\n"
        "vfnmsac.vv v10, v7, v9\n"
        "vfmul.vv v11, v6, v9\n"
        "vfmacc.vv v11, v7, v8\n"

        "vse32.v v4, (t1)\n"
        "vse32.v v5, (t2)\n"
        "vse32.v v10, (t3)\n"
        "vse32.v v11, (t4)\n"

        "addi t1, t1, 64\n"
        "addi t2, t2, 64\n"
        "addi t5, t5, -1\n"
        "bnez t5, s4_group\n"

        // ============================================================
        // Stage 5: step=8, half=4, groups=32
        // fixed vl=4
        // twiddle loaded once and reused across groups
        // twiddle offset = 992B
        // ============================================================
        "li t0, 4\n"
        "vsetvli zero, t0, e32, m1, ta, ma\n"
        "la t6, fft256_tw_re\n"
        "addi t6, t6, 992\n"
        "la a7, fft256_tw_im\n"
        "addi a7, a7, 992\n"
        "vle32.v v8, (t6)\n"
        "vle32.v v9, (a7)\n"

        "mv t1, a0\n"
        "mv t2, a1\n"
        "li t5, 32\n"

        "s5_group:\n"
        "vle32.v v0, (t1)\n"
        "vle32.v v1, (t2)\n"
        "addi t3, t1, 16\n"
        "addi t4, t2, 16\n"
        "vle32.v v2, (t3)\n"
        "vle32.v v3, (t4)\n"

        "vfadd.vv v4, v0, v2\n"
        "vfadd.vv v5, v1, v3\n"
        "vfsub.vv v6, v0, v2\n"
        "vfsub.vv v7, v1, v3\n"

        "vfmul.vv v10, v6, v8\n"
        "vfnmsac.vv v10, v7, v9\n"
        "vfmul.vv v11, v6, v9\n"
        "vfmacc.vv v11, v7, v8\n"

        "vse32.v v4, (t1)\n"
        "vse32.v v5, (t2)\n"
        "vse32.v v10, (t3)\n"
        "vse32.v v11, (t4)\n"

        "addi t1, t1, 32\n"
        "addi t2, t2, 32\n"
        "addi t5, t5, -1\n"
        "bnez t5, s5_group\n"

        // ============================================================
        // Stage 6: step=4, half=2, groups=64
        // fixed vl=2
        // twiddle loaded once and reused across groups
        // twiddle offset = 1008B
        // ============================================================
        "li t0, 2\n"
        "vsetvli zero, t0, e32, m1, ta, ma\n"
        "la t6, fft256_tw_re\n"
        "addi t6, t6, 1008\n"
        "la a7, fft256_tw_im\n"
        "addi a7, a7, 1008\n"
        "vle32.v v8, (t6)\n"
        "vle32.v v9, (a7)\n"

        "mv t1, a0\n"
        "mv t2, a1\n"
        "li t5, 64\n"

        "s6_group:\n"
        "vle32.v v0, (t1)\n"
        "vle32.v v1, (t2)\n"
        "addi t3, t1, 8\n"
        "addi t4, t2, 8\n"
        "vle32.v v2, (t3)\n"
        "vle32.v v3, (t4)\n"

        "vfadd.vv v4, v0, v2\n"
        "vfadd.vv v5, v1, v3\n"
        "vfsub.vv v6, v0, v2\n"
        "vfsub.vv v7, v1, v3\n"

        "vfmul.vv v10, v6, v8\n"
        "vfnmsac.vv v10, v7, v9\n"
        "vfmul.vv v11, v6, v9\n"
        "vfmacc.vv v11, v7, v8\n"

        "vse32.v v4, (t1)\n"
        "vse32.v v5, (t2)\n"
        "vse32.v v10, (t3)\n"
        "vse32.v v11, (t4)\n"

        "addi t1, t1, 16\n"
        "addi t2, t2, 16\n"
        "addi t5, t5, -1\n"
        "bnez t5, s6_group\n"

        // ============================================================
        // Stage 7: step=2, half=1, groups=128
        // No twiddle load needed: W = 1 + j0
        // fixed vl=1
        // ============================================================
        "li t0, 1\n"
        "vsetvli zero, t0, e32, m1, ta, ma\n"
        "mv t1, a0\n"
        "mv t2, a1\n"
        "li t5, 128\n"

        "s7_group:\n"
        "vle32.v v0, (t1)\n"
        "vle32.v v1, (t2)\n"
        "addi t3, t1, 4\n"
        "addi t4, t2, 4\n"
        "vle32.v v2, (t3)\n"
        "vle32.v v3, (t4)\n"

        "vfadd.vv v4, v0, v2\n"
        "vfadd.vv v5, v1, v3\n"
        "vfsub.vv v6, v0, v2\n"
        "vfsub.vv v7, v1, v3\n"

        "vse32.v v4, (t1)\n"
        "vse32.v v5, (t2)\n"
        "vse32.v v6, (t3)\n"
        "vse32.v v7, (t4)\n"

        "addi t1, t1, 8\n"
        "addi t2, t2, 8\n"
        "addi t5, t5, -1\n"
        "bnez t5, s7_group\n"

        "ret\n"
    );
}
