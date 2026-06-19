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
#define TEST_ELEMENTS  512

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

// Function prototype using vector extension
void vscopy(int n, const float *src, float *dst);

int main() {
    const float a = 6.66;

    vscopy(TOTAL_ELEMENTS, src1, src2);
    #ifndef SPIKE
    perf_time();
    #endif

    return 0;
}

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void vscopy(int n, const float *src, float *dst) {
    __asm__ volatile(
#ifndef SPIKE
        "rdcycle zero\n"
#endif
        "loop:\n"
        "vsetvli t0, a0, e32, m1, ta, ma\n"
        "vle32.v v0, (a1)\n"
        "sub a0, a0, t0\n"
        "slli t1, t0, 2\n"
        "add a1, a1, t1\n"
        "vse32.v v0, (a2)\n"
        "add a2, a2, t1\n"
        "bnez a0, loop\n"
        "ret\n"
    );
}
