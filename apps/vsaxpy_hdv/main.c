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

// 16-byte aligned HDV task entry used by the mock host/TB.
// Override with: make -C apps bin/vsaxpy_hdv HDV_TASK_ENTRY=0x80002000
#ifndef VSAXPY_HDV_TASK_ENTRY
#define VSAXPY_HDV_TASK_ENTRY 0x80001000UL
#endif

extern float src1[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src1")));
extern float src2[TOTAL_ELEMENTS] __attribute__((aligned(4), section(".data.src2")));

extern const uint32_t _src1_size;
extern const uint32_t _src2_size;

void vsaxpy(int n, const float a, const float *src1, float *src2);

int main() {
    const float a = 6.66;

    vsaxpy(TOTAL_ELEMENTS, a, src1, src2);
    #ifndef SPIKE
    perf_time();
    #endif

    return 0;
}

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void vsaxpy(int n, const float a, const float *src1, float *src2) {
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    /*
     * HDV_HINT emits the 32-bit packet header selected for this test.  The
     * header is the first instruction word of each 16-byte HDV fetch packet:
     *
     *   lui x0, imm20
     *
     * The HDV RTL decodes imm20 as:
     *   imm20[12:0] = pbits between 16-bit slots
     *   imm20[13]   = this logical packet consumes the next 128-bit beat too
     *   imm20[14]   = the tail EP may cross into the next logical packet
     *   imm20[15]   = loop-start marker
     *   imm20[16]   = loop-end marker
     *
     * Each 128-bit fetch packet has one 32-bit header plus three 32-bit
     * instructions.  With the current RTL NumSlots=8, one EP can contain up to
     * four 32-bit instructions.  Cross-packet packing is therefore used below
     * to carry packet 0's sub into packet 1 and form a full 4-instruction EP.
     *
     * For three 32-bit instructions in one 128-bit packet, the useful pbits
     * between complete instructions are pbits[1] and pbits[3]:
     *   HDV_HINT 0x02 means inst0 || inst1, then cut before inst2.
     *   HDV_HINT 0x0a means inst0 || inst1 || inst2.
     * The VLIW pack unit can still stop earlier for dependency, branch/system,
     * issue-width, or 32-bit instruction integrity constraints.
     */
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=0, prefetch_disable=0\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17) | (((\\prefetch_disable) & 1) << 19))\n"
    ".endm\n"
    ".balign 16\n"
    "vsaxpy_hdv_task_start:\n"

    // packet 0: EP0 = vsetvli || vle32(v0).  The cut before sub leaves sub as
    // a packet-tail carry, and cross=1 lets it join packet 1.
    "loop:\n"
    "HDV_HINT 0x02, 0, 1, 1, 0\n"
    "vsetvli t0, a0, e32, m1, ta, ma\n"
    "vle32.v v0, (a1)\n"
    "sub a0, a0, t0\n"

    // packet 1: EP1 = carried sub || vle32(v3) || slli || vfmacc.
    // vsetvli's rd=t0 is safe because EP0 waits for vset writeback before EP1.
    "HDV_HINT\n"
    "vle32.v v3, (a2)\n"
    "slli t1, t0, 2\n"
    "vfmacc.vf v3, fa0, v0\n"

    // packet 2: EP2 = add a1 || vse32(old a2) || add a2.  The store snapshots
    // the old a2 before the pointer increment in the same EP, which is intended.
    "HDV_HINT\n"
    "add a1, a1, t1\n"
    "vse32.v v3, (a2)\n"
    "add a2, a2, t1\n"

    // packet 3: EP3 is bnez only because branch/system instructions force a
    // pack cut in RTL.  On loop exit, ret becomes the final scalar EP and
    // terminates the HDV task; nop is only packet padding.
    "HDV_HINT 0x1f, 0, 0, 0, 1\n"
    "bnez a0, loop\n"
    "ret\n"
    "nop\n"
    ".purgem HDV_HINT\n"
    ".option pop\n"
    );
}
