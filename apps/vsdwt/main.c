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
#define DWT_COEFFS 512

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// input:
//   src1[i] = even samples
//   src2[i] = odd  samples
// output (in-place):
//   src1[i] = approximation
//   src2[i] = detail
void dwt_haar_f32_1024_split(float *even, float *odd);

int main() {
    dwt_haar_f32_1024_split(src1, src2);

#ifndef SPIKE
    perf_time();
#endif

    return 0;
}

#include <stdint.h>

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void dwt_haar_f32_1024_split(float *even, float *odd) {
    __asm__ volatile(
#ifndef SPIKE
        "rdcycle zero\n"
#endif
        // a0 = even
        // a1 = odd
        //
        // input:
        //   even[i] = x[2i]
        //   odd[i]  = x[2i+1]
        //
        // output in-place:
        //   even[i] = (even[i] + odd[i]) / sqrt(2)
        //   odd[i]  = (even[i] - odd[i]) / sqrt(2)
        //
        // total coefficients = 512
        // FP32, VLEN=1024, LMUL=1 => VLMAX = 32

        // remaining coefficients
        "li t0, 512\n"

        // ft0 = 1/sqrt(2) ≈ 0.70710677f = 0x3f3504f3
        "li t6, 0x3f3504f3\n"
        "fmv.w.x ft0, t6\n"

        "dwt_loop:\n"
        // vl = min(avl, 32)
        "vsetvli t1, t0, e32, m1, ta, ma\n"

        // load even / odd streams
        "vle32.v v0, (a0)\n"          // even
        "vle32.v v1, (a1)\n"          // odd

        // approximation = even + odd
        "vfadd.vv v2, v0, v1\n"

        // detail = even - odd
        "vfsub.vv v3, v0, v1\n"

        // scale by 1/sqrt(2)
        "vfmul.vf v2, v2, ft0\n"
        "vfmul.vf v3, v3, ft0\n"

        // store in-place
        "vse32.v v2, (a0)\n"
        "vse32.v v3, (a1)\n"

        // advance pointers by vl * 4
        "slli t2, t1, 2\n"
        "add a0, a0, t2\n"
        "add a1, a1, t2\n"

        // remaining -= vl
        "sub t0, t0, t1\n"
        "bnez t0, dwt_loop\n"

        "ret\n"
    );
}
