#include <stdint.h>

#ifndef VSPF_M2K2_HDV_TASK_ENTRY
#define VSPF_M2K2_HDV_TASK_ENTRY 0x80001000UL
#endif

// Prefetch micro-benchmark variant: LMUL=m2, K=2 streams, lead 3
// (1X/2X/4X = 1/2/3).  prefetch_mode chosen per the 128-beat budget fit rule
// K*L*VLMAX/4 <= 128 (see hardware/docs/prefetch_config.md).
#define PF_LMUL 2
#define PF_K    2
#define PF_MODE 1
#define PF_VS0  0
#define PF_VS1  2
#define PF_VS2  4
#define PF_VS3  6
#define PF_VR   4
#include "vspf_kernel.inc"

int main() {
    // Under HDV the TB jumps straight to the .hdv_task entry; this just keeps the
    // task function referenced for the linker.  Pointers come from +HDV_A* plusargs.
    vspf_task(0, (const float *)0, (const float *)0,
              (const float *)0, (const float *)0, (float *)0);
    return 0;
}
