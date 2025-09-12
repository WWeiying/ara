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

//enum { TOTAL_ELEMENTS = 1024};
#define TOTAL_ELEMENTS 1024

//extern int16_t source[TOTAL_ELEMENTS] __attribute__((aligned(2), section(".data.source")));
extern int32_t src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern int32_t src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));
extern int32_t dest[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.dest")));

//extern const uint32_t _source_size;
extern const uint32_t _src1_size;
extern const uint32_t _src2_size;
extern const uint32_t _dest_size;

// Function prototype using vector extension
//void vec_mul_shift(int n, const short *src, int *dst, int scalar);
void vvaddint32(int n, const int *src1, const int *src2, int *dst);

int main() {
    //const int VLEN = 256;      // Vector length in bits
    //const int ELEMENT_SIZE = 16; // Size in bits

    
    // Calculate max vector elements per segment
    //const int MAX_VECTOR_ELEMENTS = VLEN / ELEMENT_SIZE;
    
 //   int scalar_multiplier = 3;
    
    // Perform vector operation
    //vec_mul_shift(TOTAL_ELEMENTS, source, dest, scalar_multiplier);
    int64_t runtime;
    int64_t runinst;

    start_timer();    
    start_instret_counter();
    vvaddint32(TOTAL_ELEMENTS, src1, src2, dest);
    stop_timer();
    stop_instret_counter();

    runtime = get_timer();
    runinst = get_instret_counter();

    printf("\tIPC: %.3f\n\tInstret: %d\n\tCycle: %d\n", (float)runinst/runtime, runinst, runtime);

    return 0;
}

//// Vector processing function
//__attribute__((naked, target("arch=rv64gcv")))
//void vec_mul_shift(int n, const short *src, int *dst, int scalar) {
//    __asm__ volatile (
//        "mv t0, a3\n"
//        "beqz a0, exit_loop\n"
//        
//        "loop_start:\n"
//        "   vsetvli a3, a0, e16, m4, ta, ma\n"
//        "   vle16.v v4, (a1)\n"
//        "   slli t1, a3, 1\n"
//        "   add a1, a1, t1\n"
//        "   vwmul.vx v8, v4, t0\n"
//        "   vsetvli zero, zero, e32, m8, ta, ma\n"
//        "   vsrl.vi v8, v8, 3\n"
//        "   vse32.v v8, (a2)\n"
//        "   slli t1, a3, 2\n"
//        "   add a2, a2, t1\n"
//        "   sub a0, a0, a3\n"
//        "   bnez a0, loop_start\n"
//        
//        "exit_loop:\n"
//        "   ret\n"
//    );
//}

#ifdef vec
__attribute__((noinline, used)) void vvaddint32(int n, const int *src1, const int *src2, int*dst) {
#pragma clang loop vectorize(enable)
    for (int i=0; i<n; i++) {
        dst[i]=src1[i]+src2[i];
    }
}
#elif defined manual
__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void vvaddint32(int n, const int *src1, const int *src2, int*dst) {
    __asm__ volatile (
    "loop_start:\n"
    "  vsetvli t0, a0, e32, m2, ta, ma\n"
    "  vle32.v v0, (a1)\n"
    "  sub a0, a0, t0\n"
    "  slli t0, t0, 2\n"
    "  add a1, a1, t0\n"
    "  vle32.v v8, (a2)\n"
    "  add a2, a2, t0\n"
    "  vadd.vv v16, v0, v8\n"
    "  vse32.v v16, (a3)\n"
    "  add a3, a3, t0\n"
    "  bnez a0, loop_start\n"
    "  ret\n"
    );
}
#else
__attribute__((noinline, used)) void vvaddint32(int n, const int *src1, const int *src2, int*dst) {
    for (int i=0; i<n; i++) {
        dst[i]=src1[i]+src2[i];
    }
}
#endif
