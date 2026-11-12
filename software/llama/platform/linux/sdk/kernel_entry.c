#include "kernel_compute.h"

int ara_resident_compute_owned(struct ara_resident_compute_buffers *buffers);

/* Ordinary scalar kernel flags: implicit stack initialization must not use a
 * vector before the scope-owned vstart is cleared.
 */
int ara_resident_compute(struct ara_resident_compute_buffers *buffers)
{
    if (buffers == NULL)
        return -22;
    if (buffers->started != 0)
        return -5;
    if ((buffers->flags & ~ARA_RESIDENT_COMPUTE_REQUIRED_FLAGS) ||
        buffers->resident_used != 0)
        return -22;
    if (buffers->flags != ARA_RESIDENT_COMPUTE_REQUIRED_FLAGS)
        return -95;
#if defined(__riscv) && __riscv_xlen == 64
    __asm__ volatile("csrw fcsr, zero\ncsrw vcsr, zero\ncsrw vstart, zero"
                     : : : "memory");
#endif
    return ara_resident_compute_owned(buffers);
}
