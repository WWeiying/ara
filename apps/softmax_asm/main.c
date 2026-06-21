// SPDX-License-Identifier: Apache-2.0
// Plain-Ara hand-asm baseline of softmax (channel-dim, Cephes exp).
// Counterpart asm baseline of softmax_hdv; mirrors the compiler-vectorised
// softmax_vec instruction stream, cleaned into a naked function with a local
// exp constant pool.  Scalar softmax() (libm exp) is the gold reference.

#include <math.h>
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

#define CHECK
#define THRESHOLD 0.0001

extern uint64_t channels;
extern uint64_t innerSize;
extern float i[] __attribute__((aligned(4 * NR_LANES)));
extern float buf[] __attribute__((aligned(4 * NR_LANES)));
extern float o_s[] __attribute__((aligned(4 * NR_LANES)));
extern float o_v[] __attribute__((aligned(4 * NR_LANES)));

// ---- scalar gold reference (OpenCV-style softmax along channel axis) --------
static void softmax_ref(const float *in, float *out, float *bufp,
                        uint64_t ch, uint64_t inner) {
  for (uint64_t k = 0; k < inner; ++k)
    bufp[k] = in[k];
  for (uint64_t c = 1; c < ch; ++c)
    for (uint64_t k = 0; k < inner; ++k)
      bufp[k] = fmaxf(bufp[k], in[c * inner + k]);
  for (uint64_t c = 0; c < ch; ++c)
    for (uint64_t k = 0; k < inner; ++k)
      out[c * inner + k] = expf(in[c * inner + k] - bufp[k]);
  for (uint64_t k = 0; k < inner; ++k)
    bufp[k] = 0.f;
  for (uint64_t c = 0; c < ch; ++c)
    for (uint64_t k = 0; k < inner; ++k)
      bufp[k] += out[c * inner + k];
  for (uint64_t c = 0; c < ch; ++c)
    for (uint64_t k = 0; k < inner; ++k)
      out[c * inner + k] /= bufp[k];
}

// ---- plain-Ara hand-asm vector softmax (channel-dim, Cephes exp) ------------
// ABI: a0=in, a1=out, a2=channels, a3=innerSize.  e32/m1; stripmines innerSize.
void softmax_clean(const float *in, float *out, uint64_t ch, uint64_t inner);

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void softmax_clean(const float *in, float *out, uint64_t ch, uint64_t inner) {
  __asm__ volatile (
    "addi sp, sp, -16\n"
    "sd   s0, 8(sp)\n"
    "beqz a3, 9f\n"                 // innerSize == 0
    "beqz a2, 9f\n"                 // channels == 0
    "addi a7, a2, -1\n"             // channels-1
    "slli t6, a3, 2\n"              // channel byte stride = innerSize*4
    "li   a6, 2\n"
    // load exp constants from local pool
    "la   t0, softmax_clean_pool\n"
    "flw  fa5, 0(t0)\n"             // exp_hi
    "flw  fa4, 4(t0)\n"             // exp_lo
    "flw  fa3, 8(t0)\n"             // LOG2EF
    "flw  fa2, 12(t0)\n"            // C2
    "flw  fa1, 16(t0)\n"            // p0
    "flw  fa0, 20(t0)\n"            // p1
    "flw  ft0, 24(t0)\n"           // p2
    "flw  ft1, 28(t0)\n"           // p3
    "flw  ft2, 32(t0)\n"           // p4
    "lui  t0, 0x3f318\n"           // C1 = 0.693359375
    "lui  t1, 0x3f000\n"           // 0.5  (= p5)
    "lui  t2, 0x3f800\n"           // 1.0
    "li   t3, 0x7f\n"              // 127
    "li   t4, 0x17\n"              // 23
  "1:\n"                            // stripmine over innerSize
    "vsetvli t5, a3, e32, m1, ta, ma\n"
    "vle32.v v8, (a0)\n"            // first channel -> running elementwise max
    "bltu a2, a6, 3f\n"            // channels < 2 -> skip max loop
    "add  a4, a0, t6\n"
    "mv   a5, a7\n"
  "2:\n"
    "vle32.v v9, (a4)\n"
    "addi a5, a5, -1\n"
    "vfmax.vv v8, v8, v9\n"
    "add  a4, a4, t6\n"
    "bnez a5, 2b\n"
  "3:\n"                            // broadcast exp constants to vregs
    "vmv.v.i  v9, 0\n"
    "vfmv.v.f v10, fa5\n"
    "vfmv.v.f v12, fa4\n"
    "vfmv.v.f v13, fa3\n"
    "vmv.v.x  v14, t0\n"
    "vfmv.v.f v15, fa2\n"
    "vfmv.v.f v16, fa1\n"
    "vfmv.v.f v17, fa0\n"
    "vfmv.v.f v18, ft0\n"
    "vfmv.v.f v19, ft1\n"
    "vfmv.v.f v20, ft2\n"
    "vmv.v.x  v21, t1\n"
    "vmv.v.x  v22, t2\n"
    "vmv.v.x  v23, t3\n"
    "vmv.v.x  v24, t4\n"
    "mv   a5, a0\n"                 // src channel walk
    "mv   a4, a1\n"                 // dst channel walk
    "mv   s0, a2\n"                 // channel count
    "vmv1r.v v11, v9\n"             // denom accumulator = 0
  "4:\n"                            // per-channel: sub max, exp, store, accum
    "vle32.v v25, (a5)\n"
    "vfsub.vv v25, v25, v8\n"
    "vfmin.vv v25, v25, v10\n"
    "vfmax.vv v25, v25, v12\n"
    "vmv1r.v  v26, v16\n"
    "vmv1r.v  v27, v25\n"
    "vfmadd.vv v27, v13, v21\n"     // fx = x*LOG2EF + 0.5
    "vfcvt.x.f.v v28, v27\n"
    "vfcvt.f.x.v v28, v28\n"
    "vmflt.vv v0, v27, v28\n"
    "addi s0, s0, -1\n"
    "vmerge.vvm v27, v9, v22, v0\n"
    "vfsub.vv v27, v28, v27\n"      // fx = floor(fx)
    "vfmul.vv v28, v27, v14\n"      // fx*C1
    "vfsub.vv v25, v25, v28\n"
    "vfmul.vv v28, v27, v15\n"      // fx*C2
    "vfcvt.x.f.v v27, v27\n"
    "vadd.vv  v27, v27, v23\n"      // + 127
    "vfsub.vv v25, v25, v28\n"
    "vsll.vv  v27, v27, v24\n"      // << 23 -> 2^fx
    "vfmul.vv v28, v25, v25\n"      // z = x*x
    "vfmadd.vv v26, v25, v17\n"     // Horner
    "vfmadd.vv v26, v25, v18\n"
    "vfmadd.vv v26, v25, v19\n"
    "vfmadd.vv v26, v25, v20\n"
    "vfmadd.vv v26, v25, v21\n"
    "vfmadd.vv v26, v28, v25\n"     // y = y*z + x
    "vfadd.vv v25, v26, v22\n"      // + 1.0
    "vfmul.vv v25, v25, v27\n"      // * 2^fx -> exp
    "vse32.v v25, (a4)\n"
    "vfadd.vv v11, v11, v25\n"      // denom += exp
    "add  a4, a4, t6\n"
    "add  a5, a5, t6\n"
    "bnez s0, 4b\n"
    "mv   a4, a1\n"                 // divide pass
    "mv   a5, a2\n"
  "5:\n"
    "vle32.v v8, (a4)\n"
    "vfdiv.vv v8, v8, v11\n"
    "addi a5, a5, -1\n"
    "vse32.v v8, (a4)\n"
    "add  a4, a4, t6\n"
    "bnez a5, 5b\n"
    "slli a4, t5, 2\n"             // advance stripmine
    "sub  a3, a3, t5\n"
    "add  a0, a0, a4\n"
    "add  a1, a1, a4\n"
    "bnez a3, 1b\n"
  "9:\n"
    "ld   s0, 8(sp)\n"
    "addi sp, sp, 16\n"
    "ret\n"
    ".balign 4\n"
    "softmax_clean_pool:\n"
    ".float  88.3762626647949\n"   // exp_hi
    ".float -88.3762626647949\n"   // exp_lo
    ".float  1.44269504088896341\n"// LOG2EF
    ".float -2.12194440e-4\n"      // C2
    ".float  1.9875691500e-4\n"    // p0
    ".float  1.3981999507e-3\n"    // p1
    ".float  8.3334519073e-3\n"    // p2
    ".float  4.1665795894e-2\n"    // p3
    ".float  1.6666665459e-1\n"    // p4
  );
}

int main() {
  printf("\n=== SOFTMAX (asm baseline) ===\n");
  printf("Channels: %lu  Inner: %lu\n", channels, innerSize);

  softmax_ref(i, o_s, buf, channels, innerSize);

  start_timer();
  softmax_clean(i, o_v, channels, innerSize);
  stop_timer();
  printf("vector softmax_clean: %d cycles\n", (int)get_timer());

  int error = 0;
#ifdef CHECK
  for (uint64_t k = 0; k < channels * innerSize; ++k) {
    if (!similarity_check(o_s[k], o_v[k], THRESHOLD)) {
      error = 1;
      printf("Error at %lu: %f != %f\n", k, o_v[k], o_s[k]);
    }
  }
  if (!error)
    printf("Check okay. No errors.\n");
#endif
  return error;
}
