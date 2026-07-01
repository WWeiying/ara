// ── Shared HDV prefetch micro-benchmark kernel ──────────────────────────────
// Element-wise sum of PF_K unit-stride e32 streams into an output, in a loop.
// One vector load per stream per iteration = PF_K concurrent prefetch streams.
//
// The including main.c must define (all literals):
//   PF_LMUL  1|2|4|8     vector LMUL (VLMAX = LMUL*32 for e32, VLEN=1024)
//   PF_K     1|2|4       number of load streams
//   PF_MODE  0|1|2|3     prefetch lead = 1X|2X|4X|8X (HDV hint mode field)
//   PF_VS0..PF_VS3       stream vreg numbers (LMUL-group aligned)
//   PF_VR                result vreg number (LMUL-group aligned)
//
// VL is pinned to VLMAX with AVL = 2*VLMAX so the prefetch enable gate avl>=2*vl
// holds (the only AVL where the prefetcher engages — see docs/prefetch_config.md).
//
// ABI: a0=count(iterations), a1=s0, a2=s1, a3=s2, a4=s3, a5=out. All injected by
// the sweep via +HDV_A0..A5, so no data symbols are referenced.
#ifndef PF__STR
#define PF__STR(x) #x
#define PF_STR(x)  PF__STR(x)
#endif

__attribute__((naked, aligned(16), section(".hdv_task"),
               target("arch=rv64gcv_zfh_zvfh")))
void vspf_task(int count, const float *s0, const float *s1,
               const float *s2, const float *s3, float *out) {
    __asm__ volatile (
    ".option push\n"
    ".option norvc\n"
    ".option norelax\n"
    ".macro HDV_HINT pbits=0x1f, packet256=0, cross=0, loop_start=0, loop_end=0, prefetch_mode=0, prefetch_disable=0\n"
    "  lui x0, (((\\pbits) & 0x1fff) | (((\\packet256) & 1) << 13) | (((\\cross) & 1) << 14) | (((\\loop_start) & 1) << 15) | (((\\loop_end) & 1) << 16) | (((\\prefetch_mode) & 3) << 17) | (((\\prefetch_disable) & 1) << 19))\n"
    ".endm\n"
    ".balign 16\n"
    "vspf_hdv_task_start:\n"

    // setup: AVL = 2*VLMAX (= LMUL*64) -> VL = VLMAX; stride = VLMAX*4 (= LMUL*128).
    "HDV_HINT 0x00\n"
    "li t0, " PF_STR(PF_LMUL) "*64\n"
    "vsetvli zero, t0, e32, m" PF_STR(PF_LMUL) ", ta, ma\n"
    "li t1, " PF_STR(PF_LMUL) "*128\n"
    "HDV_HINT 0x0a\n"
    "mv t2, a0\n"
    "nop\n"
    "nop\n"

    ".balign 16\n"
    "pf_loop:\n"
    // stream 0 load (loop_start marker, prefetch_mode = PF_MODE lead).
    "HDV_HINT 0x00, 0, 0, 1, 0, " PF_STR(PF_MODE) "\n"
    "vle32.v v" PF_STR(PF_VS0) ", (a1)\n"
    "nop\n"
    "nop\n"
#if PF_K >= 2
    "HDV_HINT 0x00, 0, 0, 0, 0, " PF_STR(PF_MODE) "\n"
    "vle32.v v" PF_STR(PF_VS1) ", (a2)\n"
    "nop\n"
    "nop\n"
#endif
#if PF_K >= 3
    "HDV_HINT 0x00, 0, 0, 0, 0, " PF_STR(PF_MODE) "\n"
    "vle32.v v" PF_STR(PF_VS2) ", (a3)\n"
    "nop\n"
    "nop\n"
#endif
#if PF_K >= 4
    "HDV_HINT 0x00, 0, 0, 0, 0, " PF_STR(PF_MODE) "\n"
    "vle32.v v" PF_STR(PF_VS3) ", (a4)\n"
    "nop\n"
    "nop\n"
#endif
    // reduce the loaded streams into the result.
    "HDV_HINT 0x00\n"
#if PF_K == 1
    "vmv.v.v v" PF_STR(PF_VR) ", v" PF_STR(PF_VS0) "\n"
#elif PF_K == 2
    "vfadd.vv v" PF_STR(PF_VR) ", v" PF_STR(PF_VS0) ", v" PF_STR(PF_VS1) "\n"
#elif PF_K == 3
    "vfadd.vv v" PF_STR(PF_VR) ", v" PF_STR(PF_VS0) ", v" PF_STR(PF_VS1) "\n"
#else
    "vfadd.vv v" PF_STR(PF_VR) ", v" PF_STR(PF_VS0) ", v" PF_STR(PF_VS1) "\n"
#endif
    "nop\n"
    "nop\n"
#if PF_K >= 3
    "HDV_HINT 0x00\n"
    "vfadd.vv v" PF_STR(PF_VR) ", v" PF_STR(PF_VR) ", v" PF_STR(PF_VS2) "\n"
    "nop\n"
    "nop\n"
#endif
#if PF_K >= 4
    "HDV_HINT 0x00\n"
    "vfadd.vv v" PF_STR(PF_VR) ", v" PF_STR(PF_VR) ", v" PF_STR(PF_VS3) "\n"
    "nop\n"
    "nop\n"
#endif
    // store the result row.
    "HDV_HINT 0x00\n"
    "vse32.v v" PF_STR(PF_VR) ", (a5)\n"
    "nop\n"
    "nop\n"
    // advance the K stream pointers + the output by one chunk (stride t1).
    "HDV_HINT 0x0a\n"
    "add a1, a1, t1\n"
#if PF_K >= 2
    "add a2, a2, t1\n"
#else
    "nop\n"
#endif
#if PF_K >= 3
    "add a3, a3, t1\n"
#else
    "nop\n"
#endif
    "HDV_HINT 0x0a\n"
#if PF_K >= 4
    "add a4, a4, t1\n"
#else
    "nop\n"
#endif
    "add a5, a5, t1\n"
    "addi t2, t2, -1\n"
    // back-edge.
    "HDV_HINT 0x00, 0, 0, 0, 1\n"
    "bnez t2, pf_loop\n"
    "nop\n"
    "nop\n"

    "HDV_HINT\n"
    "ret\n"
    "nop\n"
    "nop\n"
    ".purgem HDV_HINT\n"
    ".option pop\n"
    );
}
