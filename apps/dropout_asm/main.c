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

extern const unsigned int N;
extern const float SCALE;
extern const float I[] __attribute__((aligned(4 * NR_LANES)));
extern const uint8_t SEL[] __attribute__((aligned(4 * NR_LANES)));
extern float o[] __attribute__((aligned(4 * NR_LANES)));

// Dropout: o[k] = SEL[k] ? I[k]*SCALE : 0.  Hand-written RVV (e32, LMUL=8),
// derived from the compiler's lowering of the intrinsics kernel and cleaned up
// (straightforward pointer strides, dead pre-loop vsetvli removed).  Plain-Ara
// baseline; dropout_hdv is the HDV-packetised counterpart.
void dropout_vec(unsigned int n, const float *in, float scale,
                 const uint8_t *sel, float *out);

int main() {
    dropout_vec(N, I, SCALE, SEL, o);
    return 0;
}

__attribute__((naked, target("arch=rv64gcv_zfh_zvfh")))
void dropout_vec(unsigned int n, const float *in, float scale,
                 const uint8_t *sel, float *out) {
    // ABI: a0=n, a1=in, fa0=scale, a2=sel, a3=out.
    __asm__ volatile (
        "beqz a0, dropout_exit\n"
        "dropout_loop:\n"
        "vsetvli a4, a0, e32, m8, ta, ma\n"
        "vlm.v v0, (a2)\n"                  // mask bits from SEL
        "vmv.v.i v24, 0\n"                  // zero output (masked-off lanes stay 0)
        "vle32.v v8, (a1)\n"                // input chunk
        "vfmul.vf v24, v8, fa0, v0.t\n"     // masked: out = sel ? in*scale : 0
        "vse32.v v24, (a3)\n"
        "slli t1, a4, 2\n"                  // float byte stride = vl*4
        "srli t2, a4, 3\n"                  // mask byte stride  = vl/8
        "sub a0, a0, a4\n"
        "add a1, a1, t1\n"
        "add a3, a3, t1\n"
        "add a2, a2, t2\n"
        "bnez a0, dropout_loop\n"
        "dropout_exit:\n"
        "ret\n"
    );
}
