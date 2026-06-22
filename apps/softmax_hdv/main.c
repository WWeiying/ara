// SPDX-License-Identifier: Apache-2.0
// HDV-packetised softmax (channel-dim, Cephes exp).  Packetised counterpart of
// softmax_asm: identical instruction stream, wrapped into 16B HDV fetch packets
// (HDV_HINT lui-x0 header + 3 slots).  Conservative p-bits (0x00: each slot its
// own EP) for first functional bring-up; exp is a dependent chain so most slots
// must stay separate anyway.  p-bit packing of the independent slots (constant
// broadcast, etc.) is a follow-up perf step.

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

#ifndef SOFTMAX_HDV_TASK_ENTRY
#define SOFTMAX_HDV_TASK_ENTRY 0x80001000UL
#endif

#define CHECK
#define THRESHOLD 0.0001

extern uint64_t channels;
extern uint64_t innerSize;
extern float i[] __attribute__((aligned(4 * NR_LANES)));
extern float buf[] __attribute__((aligned(4 * NR_LANES)));
extern float o_s[] __attribute__((aligned(4 * NR_LANES)));
extern float o_v[] __attribute__((aligned(4 * NR_LANES)));

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

void softmax_clean(const float *in, float *out, uint64_t ch, uint64_t inner);

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void softmax_clean(const float *in, float *out, uint64_t ch, uint64_t inner) {
  __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x00, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=1\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17))\n"
    ".endm\n"
    ".balign 16\n"
    "softmax_hdv_task_start:\n"

    // ---- prologue ----
    // NOTE: no stack save. Under HDV the TB enters this naked task with sp (x2)
    // uninitialised (=0); a `sd s0,8(sp)` would store to ~0xff..f8, a non-DRAM
    // address whose AXI write never completes and -- via the scalar-memory /
    // vector ordering guard -- blocks the following vector ops and wedges the
    // task. s0 may be clobbered freely here, so the save/restore is dropped.
    "HDV_HINT 0x00\n"
    "nop\n"
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "beqz a3, 9f\n"                 // innerSize == 0
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "beqz a2, 9f\n"                 // channels == 0
    "nop\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "addi a7, a2, -1\n"
    "slli t6, a3, 2\n"
    "li   a6, 2\n"
    "HDV_HINT 0x00\n"
    "la   t0, softmax_hdv_pool\n"   // auipc+addi (2 slots)
    "flw  fa5, 0(t0)\n"
    "HDV_HINT 0x00\n"
    "flw  fa4, 4(t0)\n"
    "flw  fa3, 8(t0)\n"
    "flw  fa2, 12(t0)\n"
    "HDV_HINT 0x00\n"
    "flw  fa1, 16(t0)\n"
    "flw  fa0, 20(t0)\n"
    "flw  ft0, 24(t0)\n"
    "HDV_HINT 0x00\n"
    "flw  ft1, 28(t0)\n"
    "flw  ft2, 32(t0)\n"
    "lui  t0, 0x3f318\n"            // C1
    "HDV_HINT 0x00\n"
    "lui  t1, 0x3f000\n"            // 0.5
    "lui  t2, 0x3f800\n"            // 1.0
    "li   t3, 0x7f\n"              // 127
    "HDV_HINT 0x00\n"
    "li   t4, 0x17\n"             // 23
    "nop\n"
    "nop\n"

    // ---- stripmine loop ----
    // NOTE: this kernel carries no explicit HDV_HINT loop_start/loop_end marks.
    // The IPU auto-locks on backward branches, so each loop body (strip-mine,
    // max, exp, div) is replayed without software marks; the back-edges redirect
    // and the not-taken exits drive the IPU loop-exit (scalar backend's precise
    // backward-branch resolution).  All four loops -- including the inner ones
    // that fall through to more code -- exit correctly.
    "1:\n"
    "HDV_HINT 0x00\n"
    "vsetvli t5, a3, e32, m1, ta, ma\n"
    "vle32.v v8, (a0)\n"
    "bltu a2, a6, 3f\n"            // channels < 2 -> skip max loop
    "HDV_HINT 0x00\n"
    "add  a4, a0, t6\n"
    "mv   a5, a7\n"
    "nop\n"

    // max loop over channels
    "2:\n"
    "HDV_HINT 0x00\n"
    "vle32.v v9, (a4)\n"
    "addi a5, a5, -1\n"
    "vfmax.vv v8, v8, v9\n"
    "HDV_HINT 0x00\n"
    "add  a4, a4, t6\n"
    "bnez a5, 2b\n"
    "nop\n"

    // ---- broadcast exp constants ----
    "3:\n"
    "HDV_HINT 0x00\n"
    "vmv.v.i  v9, 0\n"
    "vfmv.v.f v10, fa5\n"
    "vfmv.v.f v12, fa4\n"
    "HDV_HINT 0x00\n"
    "vfmv.v.f v13, fa3\n"
    "vmv.v.x  v14, t0\n"
    "vfmv.v.f v15, fa2\n"
    "HDV_HINT 0x00\n"
    "vfmv.v.f v16, fa1\n"
    "vfmv.v.f v17, fa0\n"
    "vfmv.v.f v18, ft0\n"
    "HDV_HINT 0x00\n"
    "vfmv.v.f v19, ft1\n"
    "vfmv.v.f v20, ft2\n"
    "vmv.v.x  v21, t1\n"
    "HDV_HINT 0x00\n"
    "vmv.v.x  v22, t2\n"
    "vmv.v.x  v23, t3\n"
    "vmv.v.x  v24, t4\n"
    "HDV_HINT 0x00\n"
    "mv   a5, a0\n"
    "mv   a4, a1\n"
    "mv   s0, a2\n"
    "HDV_HINT 0x00\n"
    "vmv1r.v v11, v9\n"
    "nop\n"
    "nop\n"

    // ---- exp loop over channels ----
    "4:\n"
    "HDV_HINT 0x00\n"
    "vle32.v v25, (a5)\n"
    "vfsub.vv v25, v25, v8\n"
    "vfmin.vv v25, v25, v10\n"
    "HDV_HINT 0x00\n"
    "vfmax.vv v25, v25, v12\n"
    "vmv1r.v  v26, v16\n"
    "vmv1r.v  v27, v25\n"
    "HDV_HINT 0x00\n"
    "vfmadd.vv v27, v13, v21\n"
    "vfcvt.x.f.v v28, v27\n"
    "vfcvt.f.x.v v28, v28\n"
    "HDV_HINT 0x00\n"
    "vmflt.vv v0, v27, v28\n"
    "addi s0, s0, -1\n"
    "vmerge.vvm v27, v9, v22, v0\n"
    "HDV_HINT 0x00\n"
    "vfsub.vv v27, v28, v27\n"
    "vfmul.vv v28, v27, v14\n"
    "vfsub.vv v25, v25, v28\n"
    "HDV_HINT 0x00\n"
    "vfmul.vv v28, v27, v15\n"
    "vfcvt.x.f.v v27, v27\n"
    "vadd.vv  v27, v27, v23\n"
    "HDV_HINT 0x00\n"
    "vfsub.vv v25, v25, v28\n"
    "vsll.vv  v27, v27, v24\n"
    "vfmul.vv v28, v25, v25\n"
    "HDV_HINT 0x00\n"
    "vfmadd.vv v26, v25, v17\n"
    "vfmadd.vv v26, v25, v18\n"
    "vfmadd.vv v26, v25, v19\n"
    "HDV_HINT 0x00\n"
    "vfmadd.vv v26, v25, v20\n"
    "vfmadd.vv v26, v25, v21\n"
    "vfmadd.vv v26, v28, v25\n"
    "HDV_HINT 0x00\n"
    "vfadd.vv v25, v26, v22\n"
    "vfmul.vv v25, v25, v27\n"
    "vse32.v v25, (a4)\n"
    "HDV_HINT 0x00\n"
    "vfadd.vv v11, v11, v25\n"
    "add  a4, a4, t6\n"
    "add  a5, a5, t6\n"
    "HDV_HINT 0x00\n"
    "bnez s0, 4b\n"
    "nop\n"
    "nop\n"

    // ---- divide loop ----
    "HDV_HINT 0x00\n"
    "mv   a4, a1\n"
    "mv   a5, a2\n"
    "nop\n"
    "5:\n"
    "HDV_HINT 0x00\n"
    "vle32.v v8, (a4)\n"
    "vfdiv.vv v8, v8, v11\n"
    "addi a5, a5, -1\n"
    "HDV_HINT 0x00\n"
    "vse32.v v8, (a4)\n"
    "add  a4, a4, t6\n"
    "nop\n"
    "HDV_HINT 0x00\n"
    "bnez a5, 5b\n"
    "nop\n"
    "nop\n"

    // ---- stripmine advance ----
    "HDV_HINT 0x00\n"
    "slli a4, t5, 2\n"
    "sub  a3, a3, t5\n"
    "add  a0, a0, a4\n"
    "HDV_HINT 0x00\n"
    "add  a1, a1, a4\n"
    "bnez a3, 1b\n"
    "nop\n"

    // ---- epilogue ----
    "9:\n"
    "HDV_HINT 0x00\n"
    "nop\n"
    "nop\n"
    "ret\n"
    "HDV_HINT 0x00\n"
    "nop\n"
    "nop\n"
    "nop\n"

    ".balign 4\n"
    "softmax_hdv_pool:\n"
    ".float  88.3762626647949\n"
    ".float -88.3762626647949\n"
    ".float  1.44269504088896341\n"
    ".float -2.12194440e-4\n"
    ".float  1.9875691500e-4\n"
    ".float  1.3981999507e-3\n"
    ".float  8.3334519073e-3\n"
    ".float  4.1665795894e-2\n"
    ".float  1.6666665459e-1\n"
    ".purgem HDV_HINT\n"
    ".option pop\n"
  );
}

int main() {
  printf("\n=== SOFTMAX (HDV) ===\n");
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
