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
#define TEST_ELEMENTS  512

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// Function prototype using vector extension
void gemv_f32_32x128(const float *matrix, const float *vector, float *dest);

int main() {
    const float a = 6.66;

    gemv_f32_32x128(src1,src2,src1);

    return 0;
}

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void gemv_f32_32x128(const float *matrix, const float *vector, float *dest) {
  __asm__ volatile(
#ifndef SPIKE
      "rdcycle zero\n"
#endif
      // Fixed-shape kernel: M=32, N=128, FP32
      "li t3, 32\n"
      "vsetvli zero, t3, e32, m1, ta, ma\n"

      // Construct x without vle: build once with vid, then replicate with vmv
      "vid.v v0\n"
      "vfcvt.f.x.v v0, v0\n"
      "vmv.v.v v1, v0\n"
      "vmv.v.v v2, v0\n"
      "vmv.v.v v3, v0\n"

      "mv t0, a0\n"       // row pointer
      "li t6, 1024\n"       // row counter
      "row_loop:\n"
      "vsetvli t5, t6, e32, m1, ta, ma\n"
      "vle32.v v4, (t0)\n"
      "addi t2, t0, 128\n"
      "vle32.v v5, (t2)\n"
      "addi t2, t0, 256\n"
      "vle32.v v6, (t2)\n"
      "addi t2, t0, 384\n"
      "vle32.v v7, (t2)\n"
      "vmv.v.i v8, 0\n"
      "vfmacc.vv v8, v4, v0\n"
      "vfmacc.vv v8, v5, v1\n"
      "vfmacc.vv v8, v6, v2\n"
      "vfmacc.vv v8, v7, v3\n"

      // horizontal reduction to scalar
      "vmv.v.i v16, 0\n"
      "vfredsum.vs v16, v8, v16\n"
      "vfmv.f.s fa0, v16\n"
      "fsw fa0, (a2)\n"

      // next row / next output
      "addi t0, t0, 512\n" // 128 * sizeof(float)
      "addi a2, a2, 4\n"
      "sub t6, t6, t5\n"
      "bnez t6, row_loop\n"
      "ret\n");
}
