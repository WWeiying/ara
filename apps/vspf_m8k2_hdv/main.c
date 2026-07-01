#include <stdint.h>

#ifndef VSPF_M8K2_HDV_TASK_ENTRY
#define VSPF_M8K2_HDV_TASK_ENTRY 0x80001000UL
#endif

// Prefetch micro-benchmark variant: LMUL=m8, K=2 streams, lead 1
// (1X/2X/4X/8X = 0/1/2/3).  prefetch_mode chosen per the 128-beat budget fit rule
// K*L*VLMAX/4 <= 128 (see hardware/docs/prefetch_config.md).
#define PF_LMUL 8
#define PF_K    2
#define PF_MODE 0
#define PF_VS0  0
#define PF_VS1  8
#define PF_VS2  16
#define PF_VS3  24
#define PF_VR   16
#include "vspf_kernel.inc"

int main() {
    // Under HDV the TB jumps straight to the .hdv_task entry; this just keeps the
    // task function referenced for the linker.  Pointers come from +HDV_A* plusargs.
    vspf_task(0, (const float *)0, (const float *)0,
              (const float *)0, (const float *)0, (float *)0);
    return 0;
}
