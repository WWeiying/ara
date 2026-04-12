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



