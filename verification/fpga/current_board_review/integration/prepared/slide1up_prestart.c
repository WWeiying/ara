#include <stdint.h>

/* Directed supplement requested by the parent, not an original Linux trial.
 * Match the real-data MASKU/SLDU repro pattern: src[i]=1000+i, old vd=91.
 * e16/m1, VL=2, vstart=1: vslide1up must produce [91,1000], not scalar
 * insertion at element zero or an overwritten prestart element. Register roles
 * v8 -> v24 and v0.t follow rvv_matrix/permutation.py's operation 18.
 */
int slide1up_prestart_main(void) {
    static uint16_t source[64] __attribute__((aligned(64)));
    static uint16_t result[64] __attribute__((aligned(64)));
    static uint8_t predicate[16] __attribute__((aligned(64)));
    unsigned long start;
    for (unsigned i = 0; i < 64; ++i) { source[i] = 1000 + i; result[i] = 91; }
    for (unsigned i = 0; i < 16; ++i) predicate[i] = 255;
    __asm__ volatile(
        "vsetvli t0,zero,e16,m1,tu,mu\n"
        "vle16.v v8,(%1)\n"
        "vle16.v v24,(%2)\n"
        "vlm.v v0,(%3)\n"
        "li t0,2\n"
        "vsetvli t0,t0,e16,m1,tu,mu\n"
        "li t1,777\n"
        "csrwi vstart,1\n"
        "vslide1up.vx v24,v8,t1,v0.t\n"
        "csrr %0,vstart\n"
        "vsetvli t0,zero,e16,m1,tu,mu\n"
        "vse16.v v24,(%2)\n"
        : "=&r"(start) : "r"(source), "r"(result), "r"(predicate)
        : "t0", "t1", "memory");
    if (start || result[0] != 91 || result[1] != 1000) return 1;
    for (unsigned i = 2; i < 64; ++i) if (result[i] != 91) return 1;
    return 0;
}
