
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
#define FFT128_TW_COUNT 127

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(128), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(128), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

extern const float fft128_tw_re[FFT128_TW_COUNT]
    __attribute__((aligned(128), section(".data.fft128_tw_re")));
extern const float fft128_tw_im[FFT128_TW_COUNT]
    __attribute__((aligned(128), section(".data.fft128_tw_im")));

extern const uint32_t _fft128_tw_re_size;
extern const uint32_t _fft128_tw_im_size;

void fft_r2dif_f32_128(float *samples_re, float *samples_im);

int main() {
#ifdef SPIKE
    if (_fft128_tw_re_size != 508 || _fft128_tw_im_size != 508) {
        printf("twiddle size mismatch: re=%u im=%u\n",
               _fft128_tw_re_size, _fft128_tw_im_size);
        return 1;
    }
#endif

    fft_r2dif_f32_128(src1, src2);

#ifndef SPIKE
    perf_time();
#endif

    return 0;
}

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void fft_r2dif_f32_128(float *samples_re, float *samples_im) {
    __asm__ volatile(
#ifndef SPIKE
        "rdcycle zero\n"
#endif
        // ============================================================
        // Stage 0: step=128, half=64
        // Use avl-driven chunking, vl=32 each time.
        // This is the only stage where avl >= 2*vl can hold.
        // Twiddle offset = 0B
        // ============================================================
        "la a2, fft128_tw_re\n"
        "la a3, fft128_tw_im\n"
        "mv t1, a0\n"                  // upper re ptr
        "mv t2, a1\n"                  // upper im ptr
        "addi t3, a0, 256\n"           // lower re ptr
        "addi t4, a1, 256\n"           // lower im ptr
        "li a4, 64\n"                  // avl = half

        "s0_chunk:\n"
        "vsetvli t0, a4, e32, m1, ta, ma\n"
        "vle32.v v0, (t1)\n"           // ur
        "vle32.v v1, (t2)\n"           // ui
        "vle32.v v2, (t3)\n"           // lr
        "vle32.v v3, (t4)\n"           // li

        "vfadd.vv v4, v0, v2\n"        // sumr
        "vfadd.vv v5, v1, v3\n"        // sumi
        "vse32.v v4, (t1)\n"
        "vse32.v v5, (t2)\n"
        "vfsub.vv v6, v0, v2\n"        // diffr
        "vfsub.vv v7, v1, v3\n"        // diffi

        "vle32.v v8, (a2)\n"           // wr
        "vle32.v v9, (a3)\n"           // wi
        "vfmul.vv v10, v6, v8\n"
        "vfnmsac.vv v10, v7, v9\n"     // lowr = diffr*wr - diffi*wi
        "vse32.v v10, (t3)\n"
        "vfmul.vv v11, v6, v9\n"
        "vfmacc.vv v11, v7, v8\n"      // lowi = diffr*wi + diffi*wr

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
        // Stage 1: step=64, half=32, groups=2
        // fixed vl=32
        // Twiddle loaded once and reused across both groups
        // Twiddle offset = 256B
        // ============================================================
        "li t0, 32\n"
        "vsetvli zero, t0, e32, m1, ta, ma\n"
        "la t6, fft128_tw_re\n"
        "addi t6, t6, 256\n"
        "la a7, fft128_tw_im\n"
        "addi a7, a7, 256\n"
        "vle32.v v8, (t6)\n"
        "vle32.v v9, (a7)\n"

        "mv t1, a0\n"
        "mv t2, a1\n"
        "li t5, 2\n"

        "s1_group:\n"
        "vle32.v v0, (t1)\n"
        "vle32.v v1, (t2)\n"
        "addi t3, t1, 128\n"
        "addi t4, t2, 128\n"

        "vle32.v v2, (t3)\n"
        "vle32.v v3, (t4)\n"
        "vfadd.vv v4, v0, v2\n"
        "vfadd.vv v5, v1, v3\n"
        "vse32.v v4, (t1)\n"
        "vse32.v v5, (t2)\n"
        "vfsub.vv v6, v0, v2\n"
        "vfsub.vv v7, v1, v3\n"

        "vfmul.vv v10, v6, v8\n"
        "vfnmsac.vv v10, v7, v9\n"
        "vse32.v v10, (t3)\n"
        "vfmul.vv v11, v6, v9\n"
        "vfmacc.vv v11, v7, v8\n"

        "vse32.v v11, (t4)\n"

        "addi t1, t1, 256\n"
        "addi t2, t2, 256\n"
        "addi t5, t5, -1\n"
        "bnez t5, s1_group\n"

        // ============================================================
        // Stage 2: step=32, half=16, groups=4
        // fixed vl=16
        // Twiddle loaded once, reused across all groups
        // Twiddle offset = 384B
        // ============================================================
        "li t0, 16\n"
        "vsetvli zero, t0, e32, m1, ta, ma\n"
        "la t6, fft128_tw_re\n"
        "addi t6, t6, 384\n"
        "la a7, fft128_tw_im\n"
        "addi a7, a7, 384\n"
        "vle32.v v8, (t6)\n"
        "vle32.v v9, (a7)\n"

        "mv t1, a0\n"
        "mv t2, a1\n"
        "li t5, 4\n"

        "s2_group:\n"
        "vle32.v v0, (t1)\n"
        "vle32.v v1, (t2)\n"
        "addi t3, t1, 64\n"
        "addi t4, t2, 64\n"
        "vle32.v v2, (t3)\n"
        "vle32.v v3, (t4)\n"

        "vfadd.vv v4, v0, v2\n"
        "vfadd.vv v5, v1, v3\n"
        "vse32.v v4, (t1)\n"
        "vse32.v v5, (t2)\n"
        "vfsub.vv v6, v0, v2\n"
        "vfsub.vv v7, v1, v3\n"

        "vfmul.vv v10, v6, v8\n"
        "vfnmsac.vv v10, v7, v9\n"
        "vse32.v v10, (t3)\n"
        "vfmul.vv v11, v6, v9\n"
        "vfmacc.vv v11, v7, v8\n"

        "vse32.v v11, (t4)\n"

        "addi t1, t1, 128\n"
        "addi t2, t2, 128\n"
        "addi t5, t5, -1\n"
        "bnez t5, s2_group\n"

        // ============================================================
        // Stage 3: step=16, half=8, groups=8
        // fixed vl=8
        // Twiddle loaded once, reused across all groups
        // Twiddle offset = 448B
        // ============================================================
        "li t0, 8\n"
        "vsetvli zero, t0, e32, m1, ta, ma\n"
        "la t6, fft128_tw_re\n"
        "addi t6, t6, 448\n"
        "la a7, fft128_tw_im\n"
        "addi a7, a7, 448\n"
        "vle32.v v8, (t6)\n"
        "vle32.v v9, (a7)\n"

        "mv t1, a0\n"
        "mv t2, a1\n"
        "li t5, 8\n"

        "s3_group:\n"
        "vle32.v v0, (t1)\n"
        "vle32.v v1, (t2)\n"
        "addi t3, t1, 32\n"
        "addi t4, t2, 32\n"
        "vle32.v v2, (t3)\n"
        "vle32.v v3, (t4)\n"

        "vfadd.vv v4, v0, v2\n"
        "vfadd.vv v5, v1, v3\n"
        "vse32.v v4, (t1)\n"
        "vse32.v v5, (t2)\n"
        "vfsub.vv v6, v0, v2\n"
        "vfsub.vv v7, v1, v3\n"

        "vfmul.vv v10, v6, v8\n"
        "vfnmsac.vv v10, v7, v9\n"
        "vfmul.vv v11, v6, v9\n"
        "vfmacc.vv v11, v7, v8\n"

        "vse32.v v10, (t3)\n"
        "vse32.v v11, (t4)\n"

        "addi t1, t1, 64\n"
        "addi t2, t2, 64\n"
        "addi t5, t5, -1\n"
        "bnez t5, s3_group\n"

        // ============================================================
        // Stage 4: step=8, half=4, groups=16
        // fixed vl=4
        // Twiddle loaded once, reused across all groups
        // Twiddle offset = 480B
        // ============================================================
        "li t0, 4\n"
        "vsetvli zero, t0, e32, m1, ta, ma\n"
        "la t6, fft128_tw_re\n"
        "addi t6, t6, 480\n"
        "la a7, fft128_tw_im\n"
        "addi a7, a7, 480\n"
        "vle32.v v8, (t6)\n"
        "vle32.v v9, (a7)\n"

        "mv t1, a0\n"
        "mv t2, a1\n"
        "li t5, 16\n"

        "s4_group:\n"
        "vle32.v v0, (t1)\n"
        "vle32.v v1, (t2)\n"
        "addi t3, t1, 16\n"
        "addi t4, t2, 16\n"
        "vle32.v v2, (t3)\n"
        "vle32.v v3, (t4)\n"

        "vfadd.vv v4, v0, v2\n"
        "vfadd.vv v5, v1, v3\n"
        "vse32.v v4, (t1)\n"
        "vse32.v v5, (t2)\n"
        "vfsub.vv v6, v0, v2\n"
        "vfsub.vv v7, v1, v3\n"

        "vfmul.vv v10, v6, v8\n"
        "vfnmsac.vv v10, v7, v9\n"
        "vfmul.vv v11, v6, v9\n"
        "vfmacc.vv v11, v7, v8\n"

        "vse32.v v10, (t3)\n"
        "vse32.v v11, (t4)\n"

        "addi t1, t1, 32\n"
        "addi t2, t2, 32\n"
        "addi t5, t5, -1\n"
        "bnez t5, s4_group\n"

        // ============================================================
        // Stage 5: step=4, half=2, groups=32
        // fixed vl=2
        // Twiddle loaded once, reused across all groups
        // Twiddle offset = 496B
        // ============================================================
        "li t0, 2\n"
        "vsetvli zero, t0, e32, m1, ta, ma\n"
        "la t6, fft128_tw_re\n"
        "addi t6, t6, 496\n"
        "la a7, fft128_tw_im\n"
        "addi a7, a7, 496\n"
        "vle32.v v8, (t6)\n"
        "vle32.v v9, (a7)\n"

        "mv t1, a0\n"
        "mv t2, a1\n"
        "li t5, 32\n"

        "s5_group:\n"
        "vle32.v v0, (t1)\n"
        "vle32.v v1, (t2)\n"
        "addi t3, t1, 8\n"
        "addi t4, t2, 8\n"
        "vle32.v v2, (t3)\n"
        "vle32.v v3, (t4)\n"

        "vfadd.vv v4, v0, v2\n"
        "vfadd.vv v5, v1, v3\n"
        "vse32.v v4, (t1)\n"
        "vse32.v v5, (t2)\n"
        "vfsub.vv v6, v0, v2\n"
        "vfsub.vv v7, v1, v3\n"

        "vfmul.vv v10, v6, v8\n"
        "vfnmsac.vv v10, v7, v9\n"
        "vse32.v v10, (t3)\n"
        "vfmul.vv v11, v6, v9\n"
        "vfmacc.vv v11, v7, v8\n"

        "vse32.v v11, (t4)\n"

        "addi t1, t1, 16\n"
        "addi t2, t2, 16\n"
        "addi t5, t5, -1\n"
        "bnez t5, s5_group\n"

        // ============================================================
        // Stage 6: step=2, half=1, groups=64
        // No twiddle load needed: W = 1 + j0
        // fixed vl=1
        // ============================================================
        "li t0, 1\n"
        "vsetvli zero, t0, e32, m1, ta, ma\n"

        "mv t1, a0\n"
        "mv t2, a1\n"
        "li t5, 64\n"

        "s6_group:\n"
        "vle32.v v0, (t1)\n"
        "vle32.v v1, (t2)\n"
        "addi t3, t1, 4\n"
        "addi t4, t2, 4\n"
        "vle32.v v2, (t3)\n"
        "vle32.v v3, (t4)\n"

        "vfadd.vv v4, v0, v2\n"
        "vfadd.vv v5, v1, v3\n"
        "vse32.v v4, (t1)\n"
        "vse32.v v5, (t2)\n"
        "vfsub.vv v6, v0, v2\n"
        "vfsub.vv v7, v1, v3\n"

        "vse32.v v6, (t3)\n"
        "vse32.v v7, (t4)\n"

        "addi t1, t1, 8\n"
        "addi t2, t2, 8\n"
        "addi t5, t5, -1\n"
        "bnez t5, s6_group\n"

        "ret\n"
    );
}
