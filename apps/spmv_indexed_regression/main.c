// Indexed FP64 SpMV followed by reductions: index EEW32 must not be scaled
// by data SEW64 when requesting index operands from each Lane.
#include <stdint.h>
#include "printf.h"
#ifndef SPMV_SCALES
#define SPMV_SCALES 1
#endif
#if SPMV_SCALES < 1 || SPMV_SCALES > 3
#error "SPMV_SCALES must be 1, 2, or 3"
#endif
#define ALIGN __attribute__((aligned(128)))
static double values[4096] ALIGN, x[256] ALIGN, y[256] ALIGN, reference[256] ALIGN;
static uint32_t offsets[4096] ALIGN, rowptr[257] ALIGN;
static void spmv(unsigned rows) {
  for (unsigned i = 0; i < rows; ++i) {
    double sum = 0;
    for (unsigned j = rowptr[i]; j < rowptr[i + 1];) {
      unsigned vl;
      asm volatile("vsetvli %0,%1,e64,m1,tu,mu"
                   : "=r"(vl) : "r"(rowptr[i + 1] - j) : "memory");
      asm volatile("vle64.v v10,(%1)\n"
                   "vle32.v v8,(%2)\n"
                   "vluxei32.v v12,(%3),v8\n"
                   "vfmul.vv v14,v10,v12\n"
                   "vfmv.s.f v0,%0\n"
                   "vfredusum.vs v1,v14,v0\n"
                   "vfmv.f.s %0,v1"
                   : "+f"(sum)
                   : "r"(values + j), "r"(offsets + j), "r"(x)
                   : "memory", "v0", "v1", "v8", "v10", "v12", "v14");
      j += vl;
    }
    y[i] = sum;
  }
}
int main(void) {
  for (unsigned scale = 0; scale < SPMV_SCALES; ++scale) {
    unsigned n = 64u << scale, avg = 4u << scale, nnz = 0;
    for (unsigned i = 0; i < n; ++i) x[i] = ((int)(i * 3 % 23) - 11) / 4.0;
    rowptr[0] = 0;
    for (unsigned i = 0; i < n; ++i) {
      unsigned count = avg / 2 + (i * 7) % (avg + 1);
      double sum = 0;
      for (unsigned j = 0; j < count; ++j) {
        unsigned col = (i * 13 + j * 17) % n;
        double value = ((int)((i + j * 3) % 17) - 8) / 4.0;
        values[nnz] = value;
        offsets[nnz++] = col * sizeof(double);
        sum += value * x[col];
      }
      rowptr[i + 1] = nnz;
      reference[i] = sum;
    }
    spmv(n);
    for (unsigned i = 0; i < n; ++i)
      if (y[i] != reference[i]) {
        printf("FAIL SpMV n=%u row=%u\n", n, i);
        return 1;
      }
    printf("PASS SpMV n=%u nnz=%u\n", n, nnz);
  }
  return 0;
}
