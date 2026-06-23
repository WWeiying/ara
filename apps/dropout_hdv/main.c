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

#ifndef DROPOUT_HDV_TASK_ENTRY
#define DROPOUT_HDV_TASK_ENTRY 0x80001000UL
#endif

extern const unsigned int N;
extern const float SCALE;
extern const float I[] __attribute__((aligned(4 * NR_LANES)));
extern const uint8_t SEL[] __attribute__((aligned(4 * NR_LANES)));
extern float o[] __attribute__((aligned(4 * NR_LANES)));

// Dropout: o[k] = SEL[k] ? I[k]*SCALE : 0.  HDV-packetised counterpart of
// dropout_asm (masked vfmul, e32/LMUL=8).
void dropout_vec(unsigned int n, const float *in, float scale,
                 const uint8_t *sel, float *out);

int main() {
    // HDV path: the mock host launches only the .hdv_task (dropout_vec) with the
    // injected args; this scalar main exists for the SPIKE build. Keep it minimal,
    // like the other HDV kernels (vsscal/vscopy): a float-printf verification bloats
    // .text past 4 KB and collides with the forced task entry at HDV_TASK_ENTRY.
    dropout_vec(N, I, SCALE, SEL, o);
#ifndef SPIKE
    perf_time();
#endif
    return 0;
}

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void dropout_vec(unsigned int n, const float *in, float scale,
                 const uint8_t *sel, float *out) {
    // ABI: a0=n, a1=in, fa0=scale, a2=sel, a3=out.
    //
    // HDV packetisation:
    //   guard = beqz n,exit
    //   EP0 = vsetvli || vlm(v0,sel) || vmv.v.i v24,0   (loop_start)
    //   EP1 = vle(v8,in) || vfmul.vf v24,v8,fa0,v0.t    (masked; fa0 stable)
    //   EP2 = vse(v24,out)
    //   EP3 = slli || srli || sub n                     (reads vsetvli rd a4, A2-safe)
    //   EP4 = add in || add out || add sel
    //   EP5 = bnez                                      (loop_end)
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=1\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17))\n"
    ".endm\n"
    ".balign 16\n"
    "dropout_hdv_task_start:\n"

    // guard: n == 0 -> exit.
    "HDV_HINT 0x00\n"
    "beqz a0, dropout_exit\n"
    "nop\n"
    "nop\n"

    // loop top: VL config || load mask || zero output accumulator.
    "dropout_loop:\n"
    "HDV_HINT 0x0a, 0, 0, 1, 0\n"
    "vsetvli a4, a0, e32, m8, ta, ma\n"
    "vlm.v v0, (a2)\n"
    "vmv.v.i v24, 0\n"
    // load input || masked multiply (out = sel ? in*scale : 0).
    "HDV_HINT 0x02\n"
    "vle32.v v8, (a1)\n"
    "vfmul.vf v24, v8, fa0, v0.t\n"
    "nop\n"
    // store output row.
    "HDV_HINT 0x00\n"
    "vse32.v v24, (a3)\n"
    "nop\n"
    "nop\n"
    // strides from granted VL (a4) + element decrement.
    "HDV_HINT 0x0a\n"
    "slli t1, a4, 2\n"
    "srli t2, a4, 3\n"
    "sub a0, a0, a4\n"
    // pointer bumps.
    "HDV_HINT 0x0a\n"
    "add a1, a1, t1\n"
    "add a3, a3, t1\n"
    "add a2, a2, t2\n"
    // back-edge.
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez a0, dropout_loop\n"
    "nop\n"
    "nop\n"

    // exit: ret terminates the HDV task.
    "dropout_exit:\n"
    "HDV_HINT\n"
    "ret\n"
    "nop\n"
    "nop\n"
    ".purgem HDV_HINT\n"
    ".option pop\n"
    );
}
